"""Synthetic state imports retain search history while excluding execution and sealed payloads."""

from __future__ import annotations

import hashlib
import copy
import datetime as dt
import json
import shutil
import sqlite3
import tempfile
import unittest
from dataclasses import asdict, replace
from contextlib import closing
from pathlib import Path
from unittest import mock

from league.swarm import cards
from league.swarm.research_state import (
    ArtifactIdentity, CaptureSelection, ExportApproval, SafeMetadataProjection, ResearchStateError, MANIFEST, WORKING_MANIFEST,
    artifact_identity, capture_snapshot, import_snapshot, assert_isolated_state, guard_tournament,
)
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, result
from league.tests.test_swarm_store import SPEC

CODE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {'signal_on': 1}\ndef decide(ctx):\n    return []\n"
SEALED = "SEALED_RESULT_VALUE_987654.321"
PRODUCTION_BOX = "sb_PRODUCTION_HANDLE_DO_NOT_ADOPT"


def reviewed_fixture_projection(archive):
    """TEST ONLY: explicit synthetic descriptions, plus exact fixture control/parameter values.

    This does not review arbitrary exports. Each use below is a synthetic fixture
    declaration; the production API has no automatic projection or approval path.
    """
    from league.swarm import research_state as state
    with closing(state._connect(Path(archive)/"swarm.sqlite")) as connection:
        source = state._metadata(connection)
    mechanisms = "Synthetic development hypothesis; original selection descriptions remain in host-only audit."
    families = []
    for row in source["families"]:
        spec = {k: v for k, v in json.loads(row["spec"]).items() if k in state._SPEC_KEYS}
        if "mechanism" in spec:
            spec["mechanism"] = mechanisms
        families.append({"id": row["id"], "mechanism": mechanisms, "spec": spec})
    projected_cards = []
    for row in source["cards"]:
        card = json.loads(row["card"])
        card.update(hypothesis=mechanisms, falsification="Synthetic predeclared negative result; original historical conclusion stays host-only.")
        card["cost"]["why"] = "Synthetic development spread and fee assumption, unchanged cost control."
        if "rebirth" in card:
            card["rebirth"].update(different="Synthetic development difference, original claim prose stays host-only.",
                                   evidence="Synthetic development evidence; original claim prose stays host-only.")
        projected_cards.append({"family": row["family"], "card": card})
    return SafeMetadataProjection(state._value_sha(source), tuple(families),
        tuple({"family": row["family"], "mechanism": mechanisms, "structure": row["structure"], "roots": json.loads(row["roots"])} for row in source["operators"]), tuple(projected_cards),
        tuple({**row, "params": json.loads(row["params"])} for row in source["versions"]),
        "Explicit synthetic fixture metadata review; no actual source export approval")


class ResearchState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[2]
        cls.actual = artifact_identity("synthetic-train-validation-checkpoint", cls.repo)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "production-fixture"
        self.audit = self.base / "host-only-audit"
        self.fresh = self.base / "isolated-working"
        self.clock = Clock()
        self.store = SwarmStore(self.source, clock=self.clock)
        self.addCleanup(self.store.close)
        self.old = ArtifactIdentity("synthetic-old-checkpoint", "synthetic-old-bundle", "a" * 64)
        self.store.put("research_evaluator", asdict(self.old))
        self.store.add_family({**SPEC, "id": "parent", "pool_token": PRODUCTION_BOX}, origin="seed")
        self.store.add_version("parent", CODE, {}, author=SEALED, note=SEALED)
        train = result("train-one")
        train.update(gym_image=self.old.image, gym_bundle=self.old.bundle, trials=7, approved_train_value="TRAIN_VISIBLE")
        self.train = self.store.add_run("parent", 1, train, window="train", stress=1, purpose="train", prune=False)
        validation = result("validation-one")
        validation["summary"]["sealed"] = SEALED
        validation.update(trials=5, gym_image=self.old.image, gym_bundle=self.old.bundle)
        self.validation = self.store.add_run("parent", 1, validation, window="validation", stress=1, purpose="validation")
        holdout = result("holdout-one")
        holdout["summary"]["sealed"] = SEALED
        holdout["sealed"] = SEALED
        self.holdout = self.store.add_run("parent", 1, holdout, window="holdout", stress=1, purpose="holdout")
        self.store.add_look("parent", 1, "b" * 64, passed=False, p_value=0.987654321, detail={"sealed": SEALED})
        self.store.add_look("parent", 1, "c" * 64, passed=True, p_value=0.00001, detail={"sealed": SEALED})
        self.store.set_state("parent", best_train_run=self.train["run_id"], best_train_version=1, gate_ready=True,
                             validation_version=1, validation_line={"passed": False, "figures": {"sealed": SEALED}},
                             validation_numbers={"pnl": 987654.321}, banded_version=1, banded_sha="c" * 64,
                             banded_evaluator=asdict(self.old), forward={"sealed": SEALED},
                             validation_verdicts={"1": {"passed": False, "at": self.store.now(), "evaluator": asdict(self.old)}},
                             look_inflight={"sha": "d" * 64, "n": 1, "box": PRODUCTION_BOX, "sealed": SEALED},
                             incubator_barred={"e" * 64: {"why": SEALED}},
                             mechanism={"failed": [1], "untestable": [2], "last": {"t": 987654.321}},
                             extension_hold={"version": 1, "at": self.clock(), "sealed": SEALED}, extension_versions=[1])
        self.store.update_family("parent", best_train=4, best_version=1, best_validation=2, validated_version=1, weight=5)
        self.store.set_band("parent", "probe", reason="historical financial qualification")
        self.store.add_family({**SPEC, "id": "child", "roots": ["QQQ"]}, origin="fork", parent="parent")
        self.store.add_version("child", CODE, {"signal_on": 0}, author="test")
        self.store.add_family({**SPEC, "id": "other"}, origin="seed")
        self.store.add_version("other", CODE + "# distinct\n", {}, author="test")
        self.store.link_lineages("parent", "other")
        self.store.refuse("parent", 1, "audit", SEALED)
        self.store.hold_look("parent", 1, "f" * 64, "holdout", SEALED)
        self.store.note("parent", SEALED)
        self.store.bury("other", SEALED, {"sealed": SEALED})
        self.store.retire("other", SEALED)
        self.store.put("pool_token", PRODUCTION_BOX)
        self.store.put("forking", {PRODUCTION_BOX: self.clock()})
        self.store.put("unsettled", {"old-provider-key": {"sealed": SEALED}})
        self.store.event("swarm.pool", None, {"box": PRODUCTION_BOX, "token": "FULL_PROVIDER_SECRET", "sealed": SEALED})
        self.store.event("swarm.status", "parent", {"action": "evaluator_adopted", "_previous_selection": {
            "validation_version": 1, "validation_line": {"passed": False, "pnl": 987654.321}, "sealed": SEALED}})
        self.store.upsert_box(PRODUCTION_BOX, kind="gym", version="production-resource-image", state="ready")
        self.store.add_forward("parent", "real", [{"id": "actual-financial-trade", "pnl": 987654.321, "max_loss": 50}])
        self.store.add_spend("sail_model", 1.19, detail={"provider_key": "old-provider-key"})
        self.store.save_convo("parent", [{"content": SEALED}], {"request": "old-provider-key"})
        for name in (".env", "swarm.pid", "provider.sqlite", "swarm.json", "gym-forward.json"):
            (self.source / name).write_text("FULL_PROVIDER_SECRET")
        self.snapshot = capture_snapshot(self.source, self.audit, snapshot_id="synthetic-snapshot-1", original_evaluator=self.old)
        self.projection = reviewed_fixture_projection(self.audit)
        self.approval = ExportApproval(self.snapshot["snapshot_id"], self.snapshot["manifest_sha256"],
                                       self.snapshot["metadata_sha256"],
                                       tuple(sorted({r["sha"] for r in self.store._all("SELECT sha FROM versions")})),
                                       (self.train["run_id"],), "synthetic host review; these bytes contain only approved development data", self.projection.sha256)

    def import_state(self, *, fresh=None, approval=None, expected=None, artifact_root=None):
        return import_snapshot(self.audit, fresh or self.fresh, runtime_scope="synthetic-research-1",
                               expected_evaluator=expected or self.actual, artifact_root=artifact_root or self.repo,
                               approval=approval or self.approval, metadata_projection=self.projection)

    def check(self, *, expected=None, artifact_root=None):
        return assert_isolated_state(self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=expected or self.actual,
                                     artifact_root=artifact_root or self.repo)

    def working_store(self):
        store = SwarmStore(self.fresh, clock=self.clock)
        self.addCleanup(store.close)
        return store

    def recapture_reviewed_fixture(self, name):
        """A new synthetic source fixture requires a new explicit metadata projection and certificate."""
        self.audit = self.base/name
        self.snapshot = capture_snapshot(self.source, self.audit, snapshot_id=name, original_evaluator=self.old)
        self.projection = reviewed_fixture_projection(self.audit)
        self.approval = replace(self.approval, snapshot_id=name, manifest_sha256=self.snapshot["manifest_sha256"],
                                metadata_sha256=self.snapshot["metadata_sha256"], safe_metadata_sha256=self.projection.sha256)

    def test_embedded_evaluation_descriptions_stay_host_only_with_both_hashes_bound(self):
        from league.tests.test_swarm_cards import CARD, MECH
        original_card = cards.validate(CARD)[0]
        original_card["hypothesis"] += " " + SEALED
        original_card["cost"]["why"] += " " + SEALED
        original_card["falsification"] += " " + SEALED
        original_card["rebirth"] = {"row": "other", "different": SEALED, "evidence": SEALED}
        original_sha = cards.put(self.store, "parent", original_card, self.store.family("parent")["structure"])
        spec = {**self.store.family("parent")["spec"], "mechanism": MECH + " " + SEALED,
                "card_sha": original_sha, "lessons": SEALED}
        self.store.update_family("parent", mechanism=MECH + " " + SEALED, spec=spec)
        self.store.update_family("child", spec={**self.store.family("child")["spec"], "card_sha": original_sha})
        self.store._exec("INSERT INTO graveyard(family,at,mechanism,structure,roots,lesson,best) VALUES(?,?,?,?,?,?,?)",
            ("op-safe-projection-fixture", self.store.now(), MECH + " " + SEALED, "debit_vertical", '["SPY"]', SEALED, "{}"))
        self.recapture_reviewed_fixture("synthetic-prose-projection")
        receipt = self.import_state()
        working = self.working_store()
        self.assertEqual(receipt["source_metadata_sha256"], self.snapshot["metadata_sha256"])
        self.assertEqual(receipt["safe_metadata_sha256"], self.projection.sha256)
        self.assertNotEqual(receipt["source_metadata_sha256"], receipt["safe_metadata_sha256"])
        self.assertIn(SEALED.encode(), (self.audit/"swarm.sqlite").read_bytes())
        self.assertNotIn(SEALED.encode(), (self.fresh/"swarm.sqlite").read_bytes())
        original_row = self.store._one("SELECT * FROM family_cards WHERE family='parent'")
        baseline = json.loads(working._one("SELECT payload FROM research_baseline WHERE kind='family_card' AND identity='parent'")["payload"])
        from league.swarm.research_state import _value_sha
        self.assertEqual(baseline["source_sha256"], _value_sha(original_row))
        self.assertEqual(baseline["source_identity_sha"], original_sha)
        self.assertEqual(working.family("child")["spec"]["card_sha"], original_sha)
        self.assertFalse(working.family("parent")["state"]["validation_verdicts"]["1"]["passed"])
        self.assertEqual(working.lineage_trials("child"), self.store.lineage_trials("child"))
        self.assertEqual(working.lineage_looks("child", include_inflight=True), self.store.lineage_looks("child", include_inflight=True))
        self.check()

    def test_projection_missing_wrong_source_and_changed_bytes_require_new_review(self):
        for projection in (None, replace(self.projection, source_metadata_sha256="0"*64),
                           replace(self.projection, provenance="different unapproved review")):
            with self.subTest(projection=projection is None), self.assertRaises(ResearchStateError):
                import_snapshot(self.audit, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                                artifact_root=self.repo, approval=self.approval, metadata_projection=projection)
            self.assertFalse(self.fresh.exists())

    def test_even_signed_projection_cannot_omit_or_add_history_or_change_controls(self):
        changes = [replace(self.projection, families=self.projection.families[:-1]),
                   replace(self.projection, families=self.projection.families + (self.projection.families[0],)),
                   replace(self.projection, version_params=self.projection.version_params[:-1])]
        for field, value in (("unreviewed_field", SEALED), ("roots", ["QQQ"]), ("prior_lineage", "fake-reset-lineage")):
            rows = copy.deepcopy(self.projection.families)
            rows[0]["spec"][field] = value
            changes.append(replace(self.projection, families=rows))
        rows = copy.deepcopy(self.projection.version_params)
        rows[0]["params"] = {"injected": SEALED}
        changes.append(replace(self.projection, version_params=rows))
        for index, projection in enumerate(changes):
            approval = replace(self.approval, safe_metadata_sha256=projection.sha256)
            with self.subTest(index=index), self.assertRaises(ResearchStateError):
                import_snapshot(self.audit, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                                artifact_root=self.repo, approval=approval, metadata_projection=projection)
            self.assertFalse(self.fresh.exists())

    def test_approved_projection_contents_are_captured_once_before_caller_mutation(self):
        from league.swarm import research_state
        original = research_state._approved_projection
        approved_sha = self.projection.sha256
        def race(*args):
            reviewed = original(*args)
            self.projection.families[0]["mechanism"] = SEALED
            return reviewed
        with mock.patch.object(research_state, "_approved_projection", side_effect=race):
            receipt = self.import_state()
        self.assertEqual(receipt["safe_metadata_sha256"], approved_sha)
        self.assertNotIn(SEALED.encode(), (self.fresh/"swarm.sqlite").read_bytes())
        self.check()

    def test_safe_card_projection_cannot_change_original_hash_controls_or_rebirth_identity(self):
        from league.tests.test_swarm_cards import CARD
        original = cards.validate(CARD)[0]
        original["rebirth"] = {"row": "other", "different": "Synthetic original difference", "evidence": "Synthetic original evidence"}
        sha = cards.put(self.store, "parent", original, self.store.family("parent")["structure"])
        self.store.update_family("parent", spec={**self.store.family("parent")["spec"], "card_sha": sha})
        self.recapture_reviewed_fixture("synthetic-card-control")
        for field, value in (("inputs", ["cross_asset"]), ("holding", "intraday"), ("unapproved", SEALED),
                             ("ablation", {"flat": True}), ("comparison", "Changed original comparison"), ("rebirth", {"row": "child", "different": "safe", "evidence": "safe"})):
            rows = copy.deepcopy(self.projection.cards)
            rows[0]["card"][field] = value
            projection = replace(self.projection, cards=rows)
            with self.subTest(field=field), self.assertRaises(ResearchStateError):
                import_snapshot(self.audit, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                                artifact_root=self.repo, approval=replace(self.approval, safe_metadata_sha256=projection.sha256),
                                metadata_projection=projection)
            self.assertFalse(self.fresh.exists())
        self.import_state()
        working = self.working_store()
        with self.assertRaises(sqlite3.IntegrityError):
            working._exec("UPDATE research_baseline SET payload='{}' WHERE kind='card_matching'")
        with self.assertRaises(sqlite3.IntegrityError):
            working._exec("INSERT INTO research_baseline VALUES('rebirth_failure','invented','{}')")
        self.check()

    def test_coherent_backup_captures_wal_rows_and_does_not_copy_runtime_files(self):
        with closing(sqlite3.connect(self.audit / "swarm.sqlite")) as snapshot:
            self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM families").fetchone()[0], 3)
            self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 3)
        self.assertFalse((self.audit / ".env").exists())
        self.assertFalse((self.audit / "swarm.sqlite-wal").exists())
        self.assertEqual((self.audit.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.audit / "swarm.sqlite").stat().st_mode & 0o777), 0o600)

    def test_selected_capture_retains_entire_lineage_and_pruned_history_without_reading_unseen_bytes(self):
        from league.swarm import research_state
        from league.swarm.incubator import save_owed
        from league.swarm.gate import run_sha
        program = self.store.version("child", 1)
        for index in range(8):
            self.store.add_run("parent", 1, result("retained-trials-"+str(index)), window="train", stress=1,
                               purpose="train")
        self.assertGreater(self.store._one("SELECT count(*) n FROM runs WHERE path IS NULL")["n"], 0)
        save_owed(self.source, {("parent", run_sha(self.store.version("parent", 1))): (1, SEALED)})
        unapproved = self.store.version("other", 1)["path"]
        (self.source/unapproved).unlink()
        (self.source/self.validation["path"]).unlink()
        (self.source/self.holdout["path"]).unlink()
        original = research_state._read_file
        def selected_only(root, relative, namespace=None):
            if Path(root) == self.source and (relative == unapproved or relative.startswith("swarm-runs/")):
                raise AssertionError("unselected program or evaluation payload was read")
            return original(root, relative, namespace)
        archive = self.base/"selected-audit"
        with mock.patch.object(research_state, "_read_file", side_effect=selected_only):
            snapshot = capture_snapshot(self.source, archive, snapshot_id="selected-lineage", original_evaluator=self.old,
                                        selection=CaptureSelection((program["sha"],), ()))
        self.assertEqual(snapshot["metadata_sha256"], self.snapshot["metadata_sha256"])
        self.assertTrue(all(row["kind"] != "run" for row in snapshot["artifacts"].values()))
        self.assertIn("incubator-bars-owed.json", snapshot["artifacts"])
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"],
                                  (program["sha"],), (), "explicit synthetic development metadata/code review only", self.projection.sha256)
        import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                        artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        for fid in ("parent", "child", "other"):
            self.assertEqual(working.lineages(fid), self.store.lineages(fid))
            self.assertEqual(working.lineage_trials(fid), self.store.lineage_trials(fid))
            self.assertEqual(working.lineage_looks(fid, include_inflight=True), self.store.lineage_looks(fid, include_inflight=True))
            for field in ("trials", "inherited_trials", "inherited_looks", "retired_at"):
                self.assertEqual(working.family(fid)[field], self.store.family(fid)[field])
        self.assertEqual(working._one("SELECT count(*) n FROM runs")["n"], self.store._one("SELECT count(*) n FROM runs")["n"])
        self.assertEqual(working.totals()["trials"], self.store.totals()["trials"])
        self.assertIn(run_sha(self.store.version("parent", 1)), working.family("parent")["state"]["incubator_barred"])
        self.assertFalse(working.family("parent")["state"]["validation_verdicts"]["1"]["passed"])
        self.assertEqual(working.family("other")["band"], "retired")
        self.assertIsNone(working.run_result(self.train["run_id"]))
        self.assertFalse((self.fresh/unapproved).exists())
        self.assertNotIn(SEALED.encode(), (self.fresh/"swarm.sqlite").read_bytes())

    def test_selected_train_receipt_and_program_require_separate_matching_export_approval(self):
        program = self.store.version("parent", 1)
        archive = self.base/"selected-train-audit"
        snapshot = capture_snapshot(self.source, archive, snapshot_id="selected-train", original_evaluator=self.old,
                                    selection=CaptureSelection((program["sha"],), (self.train["run_id"],)))
        self.assertEqual({row["run_id"] for row in snapshot["artifacts"].values() if row["kind"] == "run"},
                         {self.train["run_id"]})
        self.assertFalse((archive/self.validation["path"]).exists())
        self.assertFalse((archive/self.holdout["path"]).exists())
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"],
                                  (program["sha"],), (self.train["run_id"],), "separate synthetic exact bytes review", self.projection.sha256)
        with self.assertRaises(ResearchStateError):
            import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                            artifact_root=self.repo, metadata_projection=self.projection, approval=replace(approval, train_run_ids=(self.validation["run_id"],)))
        self.assertFalse(self.fresh.exists())
        with self.assertRaises(ResearchStateError):
            import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                            artifact_root=self.repo, metadata_projection=self.projection, approval=replace(approval, program_sha256s=(self.store.version("other", 1)["sha"],)))
        import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                        artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        self.assertEqual(self.working_store().run_result(self.train["run_id"])["approved_train_value"], "TRAIN_VISIBLE")

    def test_empty_artifact_selection_still_preserves_history_and_does_not_grant_export(self):
        archive = self.base/"metadata-only-audit"
        snapshot = capture_snapshot(self.source, archive, snapshot_id="metadata-only", original_evaluator=self.old,
                                    selection=CaptureSelection((), ()))
        self.assertEqual(snapshot["artifacts"], {})
        self.assertEqual(snapshot["metadata_sha256"], self.snapshot["metadata_sha256"])
        self.assertNotIn("export_approval", snapshot)
        approval = ExportApproval(snapshot["snapshot_id"], snapshot["manifest_sha256"], snapshot["metadata_sha256"],
                                  (), (), "explicit synthetic metadata-only review, no program or Train export", self.projection.sha256)
        with self.assertRaises(ResearchStateError):
            import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                            artifact_root=self.repo, metadata_projection=self.projection, approval=replace(approval, program_sha256s=(self.store.version("parent", 1)["sha"],)))
        import_snapshot(archive, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                        artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        self.assertEqual(working.totals()["trials"], self.store.totals()["trials"])
        self.assertEqual(working.lineage_trials("child"), self.store.lineage_trials("child"))
        self.assertFalse(list((self.fresh/"programs").rglob("*.py")))

    def test_capture_selection_rejects_bad_types_unknown_and_non_train_identities(self):
        for programs, runs in (([], ()), (("bad",), ()), (("a"*64, "a"*64), ()), ((), []),
                               ((), ("",)), ((), (" x ",)), ((), ("same", "same"))):
            with self.subTest(programs=programs, runs=runs), self.assertRaises(ResearchStateError):
                CaptureSelection(programs, runs)
        for index, selection in enumerate(({}, CaptureSelection(("f"*64,), ()), CaptureSelection((), ("unknown",)),
                                            CaptureSelection((), (self.validation["run_id"],)),
                                            CaptureSelection((), (self.holdout["run_id"],)))):
            target = self.base/("bad-selected-"+str(index))
            with self.subTest(selection=selection), self.assertRaises(ResearchStateError):
                capture_snapshot(self.source, target, snapshot_id="bad-selected", original_evaluator=self.old, selection=selection)
            self.assertFalse(target.exists())
        self.store._exec("UPDATE runs SET purpose='unreviewed' WHERE run_id=?", (self.train["run_id"],))
        with self.assertRaises(ResearchStateError):
            capture_snapshot(self.source, self.base/"bad-purpose", snapshot_id="bad-purpose", original_evaluator=self.old,
                             selection=CaptureSelection((), (self.train["run_id"],)))

    def test_selected_missing_pruned_or_changed_bytes_fail_without_partial_archive(self):
        program = self.store.version("parent", 1)
        path = self.source/program["path"]
        original = path.read_bytes()
        for change in ("missing", "changed"):
            if change == "missing": path.unlink()
            else: path.write_bytes(original+b"# changed\n")
            target = self.base/("selected-"+change)
            with self.subTest(change=change), self.assertRaises(ResearchStateError):
                capture_snapshot(self.source, target, snapshot_id="selected-bytes", original_evaluator=self.old,
                                 selection=CaptureSelection((program["sha"],), ()))
            self.assertFalse(target.exists())
            path.write_bytes(original)
        self.store._exec("UPDATE runs SET path=NULL WHERE run_id=?", (self.train["run_id"],))
        target = self.base/"selected-pruned"
        with self.assertRaises(ResearchStateError):
            capture_snapshot(self.source, target, snapshot_id="selected-pruned", original_evaluator=self.old,
                             selection=CaptureSelection((), (self.train["run_id"],)))
        self.assertFalse(target.exists())

    def test_selected_capture_detects_artifact_change_after_coherent_backup(self):
        from league.swarm import research_state
        program = self.store.version("parent", 1)
        path = self.source/program["path"]
        body = path.read_bytes()
        original = research_state._read_file
        changed = False
        def race(root, relative, namespace=None):
            nonlocal changed
            raw = original(root, relative, namespace)
            if Path(root) == self.source and relative == program["path"] and not changed:
                changed = True
                path.write_bytes(body+b"# changed after first read\n")
            return raw
        target = self.base/"selected-race"
        try:
            with mock.patch.object(research_state, "_read_file", side_effect=race), self.assertRaises(ResearchStateError):
                capture_snapshot(self.source, target, snapshot_id="selected-race", original_evaluator=self.old,
                                 selection=CaptureSelection((program["sha"],), ()))
        finally:
            path.write_bytes(body)
        self.assertFalse(target.exists())

    def test_source_state_and_artifacts_remain_unchanged_by_import(self):
        before = {table: self.store._all(f"SELECT * FROM {table}") for table in ("families", "runs", "looks", "boxes", "kv")}
        files = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*.py")}
        self.import_state()
        self.assertEqual(before, {table: self.store._all(f"SELECT * FROM {table}") for table in before})
        self.assertEqual(files, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*.py")})

    def test_lineage_trials_versions_and_consumed_looks_survive_exactly(self):
        self.import_state()
        working = self.working_store()
        for fid in ("parent", "child", "other"):
            self.assertEqual(working.lineages(fid), self.store.lineages(fid))
            self.assertEqual(working.lineage_trials(fid), self.store.lineage_trials(fid))
            self.assertEqual(working.lineage_looks(fid, include_inflight=True), self.store.lineage_looks(fid, include_inflight=True))
            for key in ("trials", "inherited_trials", "inherited_looks", "revisions", "validations"):
                self.assertEqual(working.family(fid)[key], self.store.family(fid)[key])
            self.assertEqual([(r["n"], r["sha"], r["params"]) for r in working.versions(fid)],
                             [(r["n"], r["sha"], r["params"]) for r in self.store.versions(fid)])
        self.assertEqual(working.totals()["trials"], self.store.totals()["trials"])
        self.assertEqual(working.lineage_validated("child")[0], self.store.lineage_validated("child")[0])
        self.assertTrue(working.looked("b" * 64))
        self.assertTrue(working.looked("c" * 64))

    def test_sealed_validation_forward_event_kv_and_conversation_payloads_are_absent(self):
        self.import_state()
        working = self.working_store()
        self.assertIsNone(working.run_result(self.holdout["run_id"]))
        self.assertIsNone(working.run_result(self.validation["run_id"]))
        self.assertEqual(working.run_result(self.train["run_id"])["approved_train_value"], "TRAIN_VISIBLE")
        raw = (self.fresh / "swarm.sqlite").read_bytes()
        self.assertNotIn(SEALED.encode(), raw)
        self.assertNotIn(PRODUCTION_BOX.encode(), raw)
        self.assertNotIn(b"FULL_PROVIDER_SECRET", raw)
        self.assertEqual(working.events_after(0), [])
        for table in ("boxes", "forward", "spend", "model_costs", "convo"):
            self.assertEqual(working._all(f"SELECT * FROM {table}"), [])
        self.assertIsNone(working.get("pool_token"))
        self.assertIsNone(working.get("forking"))
        self.assertFalse((self.fresh / "swarm.json").exists())
        self.assertFalse((self.fresh / "gym-forward.json").exists())

    def test_financial_qualification_and_stale_selection_are_cleared_but_failures_survive(self):
        self.import_state()
        working = self.working_store()
        fam, state = working.family("parent"), working.family("parent")["state"]
        self.assertEqual(fam["band"], "gym")
        for key in ("best_version", "best_train", "best_validation", "validated_version", "weight"):
            self.assertIsNone(fam[key])
        for key in ("banded_version", "banded_sha", "banded_evaluator", "forward", "validation_numbers"):
            self.assertNotIn(key, state)
        self.assertFalse(state["gate_ready"])
        self.assertTrue(state["gate_hold"])
        self.assertFalse(state["validation_verdicts"]["1"]["passed"])
        self.assertEqual(state["mechanism"]["failed"], [1])
        self.assertIn("e" * 64, state["incubator_barred"])
        self.assertEqual(state["look_inflight"]["sha"], "d" * 64)
        self.assertEqual(len(working.refusals("parent")), 1)
        self.assertEqual(len(working.look_holds("parent")), 1)
        self.assertEqual(working.family("other")["band"], "retired")
        self.assertEqual(working.family("other")["retired_at"], self.store.family("other")["retired_at"])
        self.assertEqual(working.get("research_evaluator"), asdict(self.actual))
        self.assertTrue(working._one("SELECT 1 FROM research_baseline WHERE kind='validation_archive'"))

    def test_historical_look_results_are_unknown_and_not_fabricated_failures(self):
        self.import_state()
        working = self.working_store()
        self.assertEqual([(r["passed"], r["p_value"]) for r in working.looks()], [(None, None), (None, None)])
        self.assertEqual([r["run_sha"] for r in working.looks()], [r["run_sha"] for r in self.store.looks()])

    def test_sql_refuses_financial_bands_adoption_forward_and_reopening_retirement(self):
        self.import_state()
        working = self.working_store()
        for operation in (
            lambda: working.set_band("parent", "probe", reason="must never activate"),
            lambda: working.set_band("parent", "candidate", reason="must never qualify"),
            lambda: working.upsert_box(PRODUCTION_BOX, kind="gym", version="old", state="ready"),
            lambda: working.add_forward("parent", "real", [{"id": "financial", "pnl": 1, "max_loss": 10}]),
            lambda: working.update_family("other", retired_at=None),
            lambda: working.add_look("parent", 1, "new-sealed-look", passed=False, p_value=None, detail={}),
        ):
            with self.assertRaises(sqlite3.IntegrityError): operation()
        self.check()

    def test_actual_artifact_fingerprints_must_match_not_just_a_caller_claim(self):
        with self.assertRaises(ResearchStateError):
            self.import_state(expected=replace(self.actual, bundle="invented-bundle"))
        with self.assertRaises(ResearchStateError):
            self.import_state(expected=replace(self.actual, execution="0" * 64))
        self.assertFalse(self.fresh.exists())

    def test_actual_source_change_invalidates_restart_even_when_image_name_is_same(self):
        artifact = self.base / "artifact-copy"
        (artifact / "league").mkdir(parents=True)
        for folder in ("gym", "live"):
            shutil.copytree(self.repo / "league" / folder, artifact / "league" / folder)
        for name in ("__init__.py", "safety.py", "structure_core.py", "stats.py"):
            shutil.copyfile(self.repo / "league" / name, artifact / "league" / name)
        self.import_state(artifact_root=artifact)
        path = artifact / "league" / "gym" / "engine.py"
        path.write_text(path.read_text() + "\n# changed semantics\n")
        with self.assertRaises(ResearchStateError): self.check(artifact_root=artifact)

    def test_explicit_export_approval_is_required_and_cannot_expose_sealed_windows(self):
        with self.assertRaises(ResearchStateError):
            import_snapshot(self.audit, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                            artifact_root=self.repo, metadata_projection=self.projection, approval=None)
        for run in (self.validation, self.holdout):
            with self.assertRaises(ResearchStateError):
                self.import_state(approval=replace(self.approval, train_run_ids=(run["run_id"],)))
            self.assertFalse(self.fresh.exists())

    def test_unapproved_programs_keep_version_identity_but_have_no_executable_payload(self):
        self.import_state(approval=replace(self.approval, program_sha256s=()))
        working = self.working_store()
        self.assertEqual(working.version("parent", 1)["sha"], self.store.version("parent", 1)["sha"])
        self.assertIsNone(working.version("parent", 1)["code"])
        self.check()

    def test_snapshot_manifest_database_and_artifact_tampering_are_refused(self):
        for kind in ("manifest", "database", "program"):
            snapshot = self.base / f"audit-{kind}"
            shutil.copytree(self.audit, snapshot)
            if kind == "manifest":
                (snapshot / MANIFEST).write_text("{}")
            elif kind == "database":
                with closing(sqlite3.connect(snapshot / "swarm.sqlite")) as conn:
                    conn.execute("UPDATE families SET trials=0 WHERE id='parent'")
                    conn.commit()
            else:
                code = snapshot / self.store.version("parent", 1)["path"]
                code.write_text(code.read_text() + "# modified\n")
            with self.assertRaises(ResearchStateError):
                import_snapshot(snapshot, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                                artifact_root=self.repo, metadata_projection=self.projection, approval=self.approval)
            self.assertFalse(self.fresh.exists())

    def test_capture_does_not_accept_a_forged_original_evaluator(self):
        target = self.base / "forged-audit"
        with self.assertRaises(ResearchStateError):
            capture_snapshot(self.source, target, snapshot_id="forged", original_evaluator=self.actual)
        self.assertFalse(target.exists())

    def test_source_audit_and_working_mount_must_be_disjoint(self):
        with self.assertRaises(ResearchStateError):
            capture_snapshot(self.source, self.source / "snapshot", snapshot_id="nested", original_evaluator=self.old)
        with self.assertRaises(ResearchStateError): self.import_state(fresh=self.audit / "controller")
        with self.assertRaises(ResearchStateError): self.import_state(fresh=self.source / "controller")
        with self.assertRaises(ResearchStateError): self.import_state(fresh=self.base)

    def test_existing_destination_is_preserved_and_never_overwritten(self):
        self.fresh.mkdir()
        marker = self.fresh / "operator-file"
        marker.write_text("keep")
        with self.assertRaises(ResearchStateError): self.import_state()
        self.assertEqual(marker.read_text(), "keep")

    def test_symlinked_program_cannot_escape_to_a_secret_file(self):
        source = self.base / "symlink-fixture"
        shutil.copytree(self.source, source)
        path = source / self.store.version("parent", 1)["path"]
        path.unlink()
        path.symlink_to(self.source / ".env")
        with self.assertRaises(ResearchStateError):
            capture_snapshot(source, self.base / "symlink-audit", snapshot_id="symlink", original_evaluator=self.old)

    def test_decreased_trials_changed_versions_and_removed_lineage_links_fail_restart(self):
        for mutation in (
            "UPDATE families SET trials=0 WHERE id='parent'",
            "UPDATE runs SET trials=0 WHERE window='train'",
            "UPDATE runs SET stress=1.5 WHERE window='validation'",
            "UPDATE families SET trials=trials+0.5 WHERE id='parent'",
            "UPDATE versions SET params='{}' WHERE family='child'",
            "DELETE FROM lineage_links",
        ):
            target = self.base / f'working-{hashlib.sha256(mutation.encode()).hexdigest()[:8]}'
            self.import_state(fresh=target)
            with closing(sqlite3.connect(target / "swarm.sqlite")) as connection:
                connection.execute(mutation)
                connection.commit()
            with self.assertRaises(ResearchStateError):
                assert_isolated_state(target, runtime_scope="synthetic-research-1", expected_evaluator=self.actual, artifact_root=self.repo)

    def test_baseline_and_consumed_look_identity_are_immutable(self):
        self.import_state()
        working = self.working_store()
        for sql in ("DELETE FROM research_baseline", "UPDATE research_baseline SET payload='{}'",
                    "INSERT INTO research_baseline VALUES('forged','origin','{}')",
                    "DELETE FROM looks", "UPDATE looks SET run_sha='erased-look'"):
            with self.assertRaises(sqlite3.IntegrityError): working._exec(sql)

    def test_historical_failure_and_retirement_seals_cannot_be_erased(self):
        for key, value in (("incubator_barred", {}), ("validation_verdicts", {}), ("mechanism", {}),
                           ("extension_hold", None), ("extension_versions", []), ("gate_hold", False)):
            target = self.base / f"mutated-{key}"
            self.import_state(fresh=target)
            store = SwarmStore(target, clock=self.clock)
            self.addCleanup(store.close)
            store.set_state("parent", **{key: value})
            with self.assertRaises(ResearchStateError):
                assert_isolated_state(target, runtime_scope="synthetic-research-1", expected_evaluator=self.actual, artifact_root=self.repo)

    def validation_rerun(self, *, historical_passed=False, current_t=20, historical_versions=1):
        """An actual adapter receipt and unchanged stock judge for a surviving historically validated version."""
        from league.swarm import settings as S
        from league.swarm.pool import GymJob
        from league.swarm.research_adapters import ResearchGymPool
        from league.swarm.tournament import Tournament
        from league.tests.test_research_adapters import Broker
        for number in range(2, historical_versions + 1):
            self.store.add_version("child", CODE, {"signal_on": number}, author="synthetic historical version")
        self.store.set_state("child", validation_verdicts={str(number): {"passed": historical_passed,
                              "at": self.store.now(), "evaluator": asdict(self.old)} for number in range(1, historical_versions + 1)})
        self.audit = self.base / "historical-validation-audit"
        self.snapshot = capture_snapshot(self.source, self.audit, snapshot_id="synthetic-validation-rerun", original_evaluator=self.old)
        self.projection = reviewed_fixture_projection(self.audit)
        self.approval = ExportApproval(self.snapshot["snapshot_id"], self.snapshot["manifest_sha256"],
            self.snapshot["metadata_sha256"], self.approval.program_sha256s, self.approval.train_run_ids, "synthetic exact review", self.projection.sha256)
        self.import_state()
        working = self.working_store()
        self.check()
        settings = copy.deepcopy(S.DEFAULTS)
        settings["researcher"]["extension_hold_checks"] = 0
        class StrongBroker(Broker):
            def run_gym(inner, job, *, key, **kwargs):
                document = super().run_gym(job, key=key, **kwargs)
                row = document["results"][0]
                row["summary"]["t_daily"] = current_t
                row["stress_1.5"]["pnl"] = 500
                inner.cache["gym", key] = copy.deepcopy(document)
                return document
        broker = StrongBroker()
        broker.image, broker.bundle, broker.execution = self.actual.image, self.actual.bundle, self.actual.execution
        pool = ResearchGymPool(working, broker, checkpoint=self.actual.image, bundle=self.actual.bundle,
                              execution=self.actual.execution, train_first="2022-01-03", roots=("SPY",), settings=settings)
        self.addCleanup(pool.stop)
        tournament = guard_tournament(Tournament(working, pool, settings, clock=self.clock), self.actual)
        version = working.version("child", 1)
        working.update_family("child", best_version=1)
        job = GymJob(family="child", version=1, code=version["code"], params=version["params"],
                     window="validation", purpose="validation", roots=("SPY",))
        landed = pool.run(job, timeout=2)
        verdict = tournament.judge("child", 1, landed)
        return working, pool, tournament, broker, verdict, landed

    def test_stock_current_validation_can_replace_latest_failed_verdict_without_erasing_history(self):
        working, _, tournament, _, verdict, _ = self.validation_rerun()
        self.assertTrue(verdict["passed"], verdict)
        self.assertTrue(working.family("child")["state"]["validation_verdicts"]["1"]["passed"])
        baseline = json.loads(working._one("SELECT payload FROM research_baseline WHERE kind='family' AND identity='child'")["payload"])
        self.assertFalse(baseline["failure_state"]["validation_verdicts"]["1"]["passed"])
        self.assertEqual(guard_tournament(tournament, self.actual), tournament, "guard installation is idempotent")
        self.check()
        row = working._one("SELECT seq FROM events WHERE kind='swarm.isolated_validation'")
        for sql in ("UPDATE events SET payload='{}' WHERE seq=?", "DELETE FROM events WHERE seq=?"):
            with self.assertRaises(sqlite3.IntegrityError): working._exec(sql, (row["seq"],))
        working.set_state("child", validation_verdicts={})
        with self.assertRaises(ResearchStateError): self.check()

    def test_current_failed_receipt_cannot_support_a_forged_latest_pass(self):
        working, _, _, _, verdict, _ = self.validation_rerun(historical_passed=True, current_t=.1)
        self.assertFalse(verdict["passed"], verdict)
        self.check()
        records = working.family("child")["state"]["validation_verdicts"]
        records["1"]["passed"] = True
        working.set_state("child", validation_verdicts=records)
        with self.assertRaises(ResearchStateError): self.check()

    def test_a_mutable_latest_pass_without_original_journal_or_receipt_stays_blocked(self):
        working, _, _, _, _, _ = self.validation_rerun()
        records = working.family("child")["state"]["validation_verdicts"]
        records["1"]["at"] = "2026-10-04T00:00:00Z"
        working.set_state("child", validation_verdicts=records)
        with self.assertRaises(ResearchStateError): self.check()

    def test_unguarded_or_unreceipted_validation_cannot_relabel_original_search_evidence(self):
        from league.swarm import settings as S
        from league.swarm.tournament import Tournament
        self.import_state()
        working = self.working_store()
        working.update_family("child", best_version=1)
        pool = mock.Mock()
        pool.image.return_value, pool.bundle.return_value = self.actual.image, self.actual.bundle
        tournament = guard_tournament(Tournament(working, pool, copy.deepcopy(S.DEFAULTS), clock=self.clock), self.actual)
        synthetic = result("not-an-actual-receipt", window="validation", t=20)
        synthetic.update(gym_image=self.actual.image, gym_bundle=self.actual.bundle, gym_execution=self.actual.execution)
        before = working.totals()
        with self.assertRaises(ResearchStateError): tournament.judge("child", 1, synthetic)
        self.assertEqual(working.totals(), before, "refused provenance never calls the stock recorder")
        self.assertEqual(working.events_after(0), [])
        working.set_state("child", validation_verdicts={"1": {"passed": True, "at": working.now(), "evaluator": asdict(self.actual)}})
        with self.assertRaises(ResearchStateError): self.check()

    def test_validation_journal_retains_original_dsr_context_when_more_versions_are_judged(self):
        from league.swarm.pool import GymJob
        working, pool, tournament, broker, _, original = self.validation_rerun()
        first = working._one("SELECT payload FROM events WHERE kind='swarm.isolated_validation' ORDER BY seq LIMIT 1")["payload"]
        version = working.add_version("child", CODE + "# new actual research version\n", {}, author="synthetic")
        working.update_family("child", best_version=version["n"])
        before = working.totals()
        with self.assertRaises(ResearchStateError): tournament.judge("child", version["n"], original)
        self.assertEqual(working.totals(), before, "another version's receipt cannot record or qualify this version")
        landed = pool.run(GymJob(family="child", version=version["n"], code=version["code"], params=version["params"],
                                window="validation", purpose="validation", roots=("SPY",)), timeout=2)
        tournament.judge("child", version["n"], landed)
        self.assertEqual(working._one("SELECT payload FROM events WHERE kind='swarm.isolated_validation' ORDER BY seq LIMIT 1")["payload"], first)
        self.assertEqual(len(broker.gym_calls), 2)
        self.check()
        working._exec("UPDATE runs SET trials=0 WHERE family='child' AND version=? AND window='validation'", (version["n"],))
        with self.assertRaises(ResearchStateError): self.check()

    def test_stock_latest_verdict_retention_does_not_erase_immutable_imported_failures(self):
        from league.swarm.pool import GymJob
        working, pool, tournament, _, _, _ = self.validation_rerun(historical_versions=64)
        version = working.add_version("child", CODE + "# version beyond latest verdict retention\n", {}, author="synthetic")
        working.update_family("child", best_version=version["n"])
        landed = pool.run(GymJob(family="child", version=version["n"], code=version["code"], params=version["params"],
                                window="validation", purpose="validation", roots=("SPY",)), timeout=2)
        tournament.judge("child", version["n"], landed)
        records = working.family("child")["state"]["validation_verdicts"]
        self.assertEqual(len(records), 64)
        baseline = json.loads(working._one("SELECT payload FROM research_baseline WHERE kind='family' AND identity='child'")["payload"])
        self.assertEqual(len(baseline["failure_state"]["validation_verdicts"]), 64)
        dropped = set(baseline["failure_state"]["validation_verdicts"]) - set(records)
        self.assertEqual(len(dropped), 1, "stock latest retention evicts one old entry")
        self.assertFalse(baseline["failure_state"]["validation_verdicts"][dropped.pop()]["passed"])
        self.check()

    def test_all_stock_failed_held_audit_and_unreadable_review_bars_survive_import(self):
        from league.swarm.incubator import family_bar
        marker = "1" * 64
        states = [
            {"gate_outcome": {"sha": marker, "result": "held", "sealed": SEALED}},
            {"review": {"sha": marker, "verdict": "pass", "audit": {"verdict": "fail", "sealed": SEALED}}},
            {"review": {"sha": marker, "verdict": "pass", "audit": {"sealed": SEALED}}},
            {"incubator_reviews": {marker: {"sha": marker, "verdict": "pass", "audit": {"verdict": "fail", "sealed": SEALED}}}},
            {"review": {"verdict": "fail", "sealed": SEALED}},
            {"review": [SEALED]},
        ]
        for index, state in enumerate(states):
            self.store.update_family("child", state=state)
            audit = self.base / f"bar-audit-{index}"
            snapshot = capture_snapshot(self.source, audit, snapshot_id=f"bar-{index}", original_evaluator=self.old)
            approval = replace(self.approval, snapshot_id=snapshot["snapshot_id"], manifest_sha256=snapshot["manifest_sha256"],
                               metadata_sha256=snapshot["metadata_sha256"])
            target = self.base / f"bar-working-{index}"
            import_snapshot(audit, target, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                            artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
            store = SwarmStore(target, clock=self.clock)
            self.addCleanup(store.close)
            imported = store.family("child")["state"]
            if index < 4:
                self.assertIn(marker, imported["incubator_barred"])
            else:
                self.assertIsNotNone(family_bar(imported))
            self.assertNotIn(SEALED.encode(), (target / "swarm.sqlite").read_bytes())

    def test_unbackfilled_events_third_unclear_attempts_and_external_owed_bars_survive(self):
        from league.swarm.gate import run_sha
        from league.swarm.incubator import save_owed
        child_sha = run_sha(self.store.version("child", 1))
        other_sha = run_sha(self.store.version("other", 1))
        parent_sha = run_sha(self.store.version("parent", 1))
        self.store.event("swarm.gate", "child", {"action": "review", "version": 1, "verdict": "fail", "sealed": SEALED})
        self.store.put("audit_attempt:old-profile:" + other_sha, 3)
        save_owed(self.source, {("parent", parent_sha): (1, SEALED)})
        snapshot = capture_snapshot(self.source, self.base / "owed-audit", snapshot_id="owed-bars", original_evaluator=self.old)
        approval = replace(self.approval, snapshot_id=snapshot["snapshot_id"], manifest_sha256=snapshot["manifest_sha256"],
                           metadata_sha256=snapshot["metadata_sha256"])
        import_snapshot(self.base / "owed-audit", self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                        artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        for fid, sha in (("child", child_sha), ("other", other_sha), ("parent", parent_sha)):
            self.assertIn(sha, working.family(fid)["state"]["incubator_barred"])
        self.assertFalse((self.fresh / "incubator-bars-owed.json").exists())
        self.assertTrue((self.base / "owed-audit" / "incubator-bars-owed.json").exists())
        self.assertNotIn(SEALED.encode(), (self.fresh / "swarm.sqlite").read_bytes())
        self.assertIsNone(working.get("audit_attempt:old-profile:" + other_sha))
        self.check()

    def test_unreadable_external_failure_reservations_preserve_the_family_wide_bar(self):
        from league.swarm.incubator import family_bar
        (self.source / "incubator-bars-owed.json").write_text(json.dumps({"bars": SEALED}))
        snapshot = capture_snapshot(self.source, self.base / "unreadable-owed-audit", snapshot_id="unreadable-owed", original_evaluator=self.old)
        approval = replace(self.approval, snapshot_id=snapshot["snapshot_id"], manifest_sha256=snapshot["manifest_sha256"],
                           metadata_sha256=snapshot["metadata_sha256"])
        import_snapshot(self.base / "unreadable-owed-audit", self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                        artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        for family in working.families():
            self.assertIsNotNone(family_bar(family["state"]))
        self.assertNotIn(SEALED.encode(), (self.fresh / "swarm.sqlite").read_bytes())
        self.check()

    def test_dropping_sql_walls_or_retirement_evidence_fails_preflight(self):
        for sql in ("DROP TRIGGER isolation_boxes_insert", "DELETE FROM graveyard", "DELETE FROM refusals",
                    "DELETE FROM look_holds", "UPDATE families SET retire_reason='reset' WHERE id='other'"):
            target = self.base / f'wall-{hashlib.sha256(sql.encode()).hexdigest()[:8]}'
            self.import_state(fresh=target)
            with closing(sqlite3.connect(target / "swarm.sqlite")) as conn:
                conn.execute(sql)
                conn.commit()
            with self.assertRaises(ResearchStateError):
                assert_isolated_state(target, runtime_scope="synthetic-research-1", expected_evaluator=self.actual, artifact_root=self.repo)

    def test_unscoped_cost_reports_and_copied_provider_keys_fail_preflight(self):
        for mutate in (
            lambda store: store.add_spend("sail_model", 1.19, detail={"source": "copied production bill"}),
            lambda store: store.put("unsettled", {"old-provider-key": {}}),
            lambda store: store._exec("INSERT INTO model_costs VALUES('old-provider-key',1.19,1)"),
        ):
            target = self.base / f"bad-report-{len(list(self.base.glob('bad-report-*')))}"
            self.import_state(fresh=target)
            store = SwarmStore(target, clock=self.clock)
            self.addCleanup(store.close)
            mutate(store)
            with self.assertRaises(ResearchStateError):
                assert_isolated_state(target, runtime_scope="synthetic-research-1", expected_evaluator=self.actual, artifact_root=self.repo)

    def test_retirement_category_still_informs_the_stock_rebirth_index(self):
        from league.swarm.architect import tag_of
        from league.swarm.mechanism import MARK
        self.store.update_family("other", retire_reason=f"{MARK}: {SEALED}")
        snapshot = capture_snapshot(self.source, self.base / "mechanism-audit", snapshot_id="mechanism-retirement", original_evaluator=self.old)
        approval = replace(self.approval, snapshot_id=snapshot["snapshot_id"], manifest_sha256=snapshot["manifest_sha256"],
                           metadata_sha256=snapshot["metadata_sha256"])
        import_snapshot(self.base / "mechanism-audit", self.fresh, runtime_scope="synthetic-research-1",
                        expected_evaluator=self.actual, artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        family = working.family("other")
        graveyard = working._one("SELECT * FROM graveyard WHERE family='other'")
        self.assertEqual(tag_of(graveyard, family), "MECHANISM")
        self.assertNotIn(SEALED, family["retire_reason"])
        self.assertNotIn(SEALED, graveyard["lesson"])
        self.check()

    def test_operator_only_failure_evidence_is_preserved_without_inventing_a_family(self):
        from league.swarm.architect import tag_of
        self.store._exec("INSERT INTO graveyard(family,at,mechanism,structure,roots,lesson,best) VALUES(?,?,?,?,?,?,?)",
                         ("op-premium-refutation", self.store.now(), "Volatility risk premium compensates selling index condors.",
                          "iron_condor", '["SPY"]', SEALED, json.dumps({"sealed": SEALED})))
        snapshot = capture_snapshot(self.source, self.base / "operator-audit", snapshot_id="operator-retirement", original_evaluator=self.old)
        self.projection = reviewed_fixture_projection(self.base / "operator-audit")
        approval = replace(self.approval, snapshot_id=snapshot["snapshot_id"], manifest_sha256=snapshot["manifest_sha256"],
                           metadata_sha256=snapshot["metadata_sha256"], safe_metadata_sha256=self.projection.sha256)
        import_snapshot(self.base / "operator-audit", self.fresh, runtime_scope="synthetic-research-1",
                        expected_evaluator=self.actual, artifact_root=self.repo, metadata_projection=self.projection, approval=approval)
        working = self.working_store()
        self.assertIsNone(working.family("op-premium-refutation"))
        row = working._one("SELECT * FROM graveyard WHERE family='op-premium-refutation'")
        self.assertEqual(tag_of(row, None), "OPERATOR")
        self.assertNotIn(SEALED, row["lesson"])
        self.assertEqual(row["best"], "{}")
        self.assertIn("op-premium-refutation", cards.RebirthIndex(working).by_id)
        self.check()

    def test_legacy_operator_structure_cells_stay_exact_and_cannot_be_remapped_by_projection(self):
        from league.swarm.research_state import _LEGACY_OPERATOR_STRUCTURES
        from league.swarm import mechanism
        for index, structure in enumerate(sorted(_LEGACY_OPERATOR_STRUCTURES)):
            self.store._exec("INSERT INTO graveyard(family,at,mechanism,structure,roots,lesson,best) VALUES(?,?,?,?,?,?,?)",
                (f"op-legacy-{index}", self.store.now(), "Volatility risk premium from implied variance", structure,
                 '["SPY"]', mechanism.MARK + ": " + SEALED, "{}"))
        original = cards.RebirthIndex(self.store)
        self.recapture_reviewed_fixture("synthetic-legacy-operator")
        rows = copy.deepcopy(self.projection.operators)
        rows[0]["structure"] = "iron_condor"
        changed = replace(self.projection, operators=rows)
        with self.assertRaises(ResearchStateError):
            import_snapshot(self.audit, self.fresh, runtime_scope="synthetic-research-1", expected_evaluator=self.actual,
                artifact_root=self.repo, approval=replace(self.approval, safe_metadata_sha256=changed.sha256), metadata_projection=changed)
        self.assertFalse(self.fresh.exists())
        self.import_state()
        projected = cards.RebirthIndex(self.working_store())
        for fid in original.by_id:
            self.assertEqual(projected.by_id[fid]["key"], original.by_id[fid]["key"])
        self.check()

    def test_stock_research_mutations_and_normal_train_pruning_remain_usable(self):
        from league.swarm import settings as S
        from league.swarm.architect import Architect
        from league.swarm.research_adapters import ResearchGymPool, ResearchModelRouter
        from league.swarm.research_controller import ControllerConfig, ResearchController
        from league.swarm.researcher import Researcher, migrate_objective
        from league.swarm.tournament import Tournament
        from league.tests.test_research_adapters import Broker
        self.import_state()
        working = self.working_store()
        self.clock.t = dt.datetime(2026, 10, 4, 10, tzinfo=dt.timezone.utc).timestamp()
        settings = copy.deepcopy(S.DEFAULTS)
        settings["researcher"].update(claude_top=0, top_families=0, rewrites_per_day=0)
        settings["tournament"].update(require_robustness=False, drift_screen=False)
        settings["population"].update(floor=0)
        settings["architect"].update(require_card=False, max_alive_per_class=0, birth_quota=None)
        broker = Broker()
        broker.image, broker.bundle, broker.execution = self.actual.image, self.actual.bundle, self.actual.execution
        router = ResearchModelRouter(working, broker, settings=settings)
        pool = ResearchGymPool(working, broker, checkpoint=self.actual.image, bundle=self.actual.bundle, execution=self.actual.execution,
                               train_first="2022-01-03", roots=("SPY",), settings=settings)
        self.addCleanup(pool.stop)
        migrate_objective(working, settings=settings)
        self.check()
        self.assertFalse(working.family("child")["state"]["gate_hold"])
        self.assertTrue(working.family("parent")["state"]["gate_hold"])
        survivor = Researcher(working, router, pool, settings, clock=self.clock, background=False)
        broker.responses = [[{"type": "function_call", "name": "gym_run", "call_id": "survivor-train-call",
                              "arguments": json.dumps({"code": CODE, "params": {"signal_on": 1}})}],
                            [{"type": "message", "content": [{"type": "output_text", "text": "Synthetic survivor turn complete."}]}]]
        broker.open_runtime = lambda: {"scope": "synthetic-research-1", "daily_budget": {"within_cap": True, "room_nanos": 1}}
        class Idle:
            def due(self):
                return False
        controller = ResearchController(working, broker, ControllerConfig("synthetic-research-1"),
                                        researcher=survivor, tournament=Idle(), architect=Idle(),
                                        verify_state=self.check, clock=self.clock)
        before_survivor = working.family("child")["trials"]
        with mock.patch.dict("os.environ", {}, clear=True):
            tick = controller.step()
        self.assertEqual(tick["status"], "running", tick)
        self.assertEqual(controller.last_family, "child")
        for job, _, _ in list(pool._jobs.values()):
            pool.wait(job, 2)
        self.assertGreater(working.family("child")["trials"], before_survivor)
        self.check()
        architect = Architect(working, router, settings, clock=self.clock)
        born = architect.admit([{**SPEC, "slug": "synthetic-new-research", "mechanism":
                                 "Synthetic distinct liquidity compensation hypothesis for ordinary offline research."}])
        self.assertEqual(len(born), 1)
        self.check()
        fid = born[0]
        broker.responses = [[{"type": "function_call", "name": "gym_run", "call_id": "new-train-call",
                              "arguments": json.dumps({"code": CODE.replace("'signal_on': 1", "'signal_on': 0"), "params": {}})}],
                            [{"type": "message", "content": [{"type": "output_text", "text": "Synthetic research turn complete."}]}]]
        researcher = Researcher(working, router, pool, settings, clock=self.clock,
                                starter=lambda _: (CODE, {}), background=False)
        cycle = researcher.cycle(fid)
        self.assertNotIn("error", cycle, cycle)
        self.assertEqual((cycle["model_calls"], cycle["tool_calls"]), (2, 1))
        for job, _, _ in list(pool._jobs.values()):
            pool.wait(job, 2)
        self.assertGreater(working.family(fid)["trials"], 0)
        self.assertTrue(working.convo(fid)[0])
        self.check()
        tournament = guard_tournament(Tournament(working, pool, settings, clock=self.clock), self.actual)
        tournament.run()
        self.check()
        # Stock model tooling books fresh local receipts; the host gate remains the admission authority.
        router.sail("flash_asap", [{"role": "user", "content": "synthetic fresh research request"}], family=fid, key="fresh-report")
        self.assertEqual(working.spent(["sail_model"]), 0.005)
        working._exec("INSERT INTO model_costs VALUES('fresh-report',0.001,1)")
        self.check()
        before_trials, before_looks = working.lineage_trials("parent"), working.lineage_looks("parent", include_inflight=True)
        for i in range(8):
            run = result(f"new-prunable-{i}")
            run.update(gym_image=self.actual.image, gym_bundle=self.actual.bundle)
            working.add_run("parent", 1, run, window="train", stress=1, purpose="train")
        self.assertIsNone(working.run(self.train["run_id"])["path"])
        self.assertEqual(working.lineage_trials("parent"), before_trials + 8)
        self.assertEqual(working.lineage_looks("parent", include_inflight=True), before_looks)
        working.add_family({**SPEC, "id": "new-descendant"}, origin="fork", parent="parent")
        working.link_lineages("parent", fid)
        self.check()
        self.assertTrue(tournament.retire(working.family("child"), "synthetic new research retirement"))
        self.check()

    def test_releasing_an_inflight_look_fails_restart(self):
        self.import_state()
        working = self.working_store()
        working.set_state("parent", look_inflight=None)
        with self.assertRaises(ResearchStateError): self.check()

    def test_import_transaction_failure_leaves_no_working_state_and_retains_raw_audit(self):
        with mock.patch("league.swarm.research_state._protect", side_effect=RuntimeError("synthetic import failure")):
            with self.assertRaises(RuntimeError): self.import_state()
        self.assertFalse(self.fresh.exists())
        self.assertTrue((self.audit / MANIFEST).exists())

    def test_runtime_scope_and_ownership_token_are_new_for_each_independent_clone(self):
        a = self.import_state()
        b = self.import_state(fresh=self.base / "second-clone")
        self.assertNotEqual(a["runtime_ownership_token"], b["runtime_ownership_token"])
        self.assertNotEqual(a["runtime_ownership_token"], self.store.get("pool_token"))
        self.assertEqual(a["snapshot_manifest_sha256"], b["snapshot_manifest_sha256"])
        with self.assertRaises(ResearchStateError):
            assert_isolated_state(self.fresh, runtime_scope="some-other-scope", expected_evaluator=self.actual, artifact_root=self.repo)


if __name__ == "__main__":
    unittest.main()

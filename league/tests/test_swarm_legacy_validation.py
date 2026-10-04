"""Offline checks for historical swarm accounting and interrupted Validation records."""

from __future__ import annotations

import copy
import datetime as dt
import gzip
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.swarm.researcher import awaiting_validation
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock, result

SPEC = {"id": "synthetic-interrupted", "mechanism": "An invented mechanism used only for accounting fixtures.",
        "structure": "iron_condor", "roots": ["SPY"]}


class IncurredSpend(unittest.TestCase):
    def test_delayed_box_receipts_stay_on_their_incurred_utc_days(self):
        midnight = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc).timestamp()
        clock = Clock(midnight + 600)
        with tempfile.TemporaryDirectory() as directory:
            store = SwarmStore(Path(directory), clock=clock)
            try:
                with store.atomic():
                    store.add_spend("gym_box", .02, at=midnight - 1, detail={"interval": "before midnight"})
                    store.add_spend("gym_box", .03, at=midnight, detail={"interval": "after midnight"})
                self.assertAlmostEqual(store.spent(["gym_box"]), .05)
                self.assertAlmostEqual(store.spent(["gym_box"], since=midnight), .03)
                rows = store._all("SELECT at,epoch,usd FROM spend ORDER BY seq")
                self.assertEqual([r["at"] for r in rows], ["2026-10-03T23:59:59Z", "2026-10-04T00:00:00Z"])
                self.assertEqual([r["epoch"] for r in rows], [midnight - 1, midnight])
                store.add_spend("gym_box", .01)
                self.assertAlmostEqual(store.spent(["gym_box"], since=clock()), .01,
                                       "callers that omit at still book at the store's clock")
            finally:
                store.close()


class LegacyInterruption(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)

    def interrupted(self, fid="synthetic-interrupted", *, stress=False):
        fam = self.store.add_family({**SPEC, "id": fid}, origin="synthetic")
        fid = fam["id"]
        version = self.store.add_version(fid, "def decide(ctx):\n    return []\n", {}, author="synthetic")
        self.store.add_run(fid, version["n"], result(f"{fid}-train"), window="train", stress=1.0, purpose="train")
        payload = {"run_id": f"{fid}-error", "status": "error", "trials": 0, "summary": {},
                   "gym_image": "invented-image", "gym_bundle": "invented-bundle"}
        if stress:
            payload["stress_1.5"] = {"status": "error", "reason": "invented interruption"}
        row = self.store.add_run(fid, version["n"], payload, window="validation", stress=1.0, purpose="validation")
        if stress:
            self.store.add_run(fid, version["n"], {"run_id": f"{row['run_id']}-s15", "status": "error", "trials": 0,
                                                 "summary": payload["stress_1.5"]},
                               window="validation", stress=1.5, purpose="validation")
        self.store.update_family(fid, best_version=version["n"], validated_version=version["n"], validations=1)
        self.store.set_state(fid, validation_version=version["n"], validation_line={"passed": False},
                             validation_view={"line_met": False, "checks_passed": 0},
                             validation_image=payload["gym_image"], validation_bundle=payload["gym_bundle"],
                             validation_verdicts={str(version["n"]): {"passed": False, "at": row["at"], "evaluator": None}},
                             validation_numbers={"mean": None, "t": None, "sharpe_daily": None, "quarters": None},
                             validation_inherited=None, typical_max_loss_usd=None, typical_by_version={},
                             validated_trials=self.store.family(fid)["trials"], validated_cycles=7,
                             dormant_cycles=0, worked_cycles=9, unrelated={"kept": True})
        return fid, row

    def assert_refused_unchanged(self, fid):
        before, events = self.store.family(fid), self.store.events_after(0)
        preview = self.store.repair_interrupted_validation(fid)
        self.assertFalse(preview["eligible"], preview)
        self.assertTrue(preview["reason"])
        self.assertFalse(self.store.repair_interrupted_validation(fid, apply=True)["applied"])
        self.assertEqual(self.store.family(fid), before)
        self.assertEqual(self.store.events_after(0), events)

    def test_preview_then_explicit_apply_preserves_provenance_and_releases_only_the_retry(self):
        fid, row = self.interrupted()
        before = self.store.family(fid)
        raw_path = self.root / row["path"]
        receipt = raw_path.read_bytes()
        counts = self.store.totals(), self.store.lineage_trials(fid), self.store.lineage_validated(fid)
        self.assertFalse(awaiting_validation(before))
        preview = self.store.repair_interrupted_validation(fid)
        self.assertTrue(preview["eligible"])
        self.assertFalse(preview["applied"])
        self.assertEqual(self.store.family(fid), before)
        self.assertEqual(self.store.events_after(0), [])
        applied = self.store.repair_interrupted_validation(fid, apply=True)
        after = self.store.family(fid)
        self.assertTrue(applied["applied"])
        self.assertEqual((after["validated_version"], after["validations"]), (None, 0))
        self.assertTrue(awaiting_validation(after))
        self.assertEqual((after["best_version"], after["trials"], after["band"]),
                         (before["best_version"], before["trials"], "gym"))
        self.assertEqual(after["state"]["unrelated"], {"kept": True})
        self.assertEqual((after["state"]["dormant_cycles"], after["state"]["worked_cycles"]), (0, 9),
                         "unrecoverable historical dormancy and worked clocks are not guessed")
        self.assertNotIn("validated_trials", after["state"])
        self.assertNotIn("validated_cycles", after["state"])
        self.assertEqual((self.store.totals(), self.store.lineage_trials(fid), self.store.lineage_validated(fid)), counts)
        self.assertEqual(raw_path.read_bytes(), receipt)
        self.assertEqual(self.store.run(row["run_id"])["status"], "error")
        [audit] = self.store.events_after(0)
        self.assertEqual(audit["kind"], "swarm.validation_interruption_repaired")
        self.assertEqual(audit["payload"]["before"], before)
        self.assertEqual(audit["payload"]["runs"][0]["path"], row["path"])
        self.assertFalse(self.store.repair_interrupted_validation(fid, apply=True)["applied"])
        self.assertEqual(len(self.store.events_after(0)), 1, "a second invocation makes no second correction")

    def test_apply_failure_rolls_back_family_and_audit_together(self):
        fid, _ = self.interrupted()
        before = self.store.family(fid)
        with mock.patch.object(self.store, "event", side_effect=sqlite3.OperationalError("invented audit failure")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "invented audit failure"):
                self.store.repair_interrupted_validation(fid, apply=True)
        self.assertEqual(self.store.family(fid), before)
        self.assertEqual(self.store.events_after(0), [])
        self.assertTrue(self.store.repair_interrupted_validation(fid)["eligible"])

    def test_a_completed_retry_counts_once_after_explicit_correction(self):
        fid, row = self.interrupted()
        original = (self.root / row["path"]).read_bytes()
        self.store.repair_interrupted_validation(fid, apply=True)
        pool = SimpleNamespace(image=lambda kind="gym": "invented-image", bundle=lambda: "invented-bundle")
        tournament = Tournament(self.store, pool, copy.deepcopy(DEFAULTS), clock=self.clock)
        done = {**result("invented-completed-retry", window="validation", pnl=-10, mean=-.1, t=-1),
                "run_id": row["run_id"], "gym_image": "invented-image", "gym_bundle": "invented-bundle"}
        verdict = tournament.judge(fid, 1, done)
        after = self.store.family(fid)
        self.assertFalse(verdict["passed"], "the invented completed failure remains a real failed verdict")
        self.assertEqual((after["validated_version"], after["validations"], after["trials"]), (1, 1, 3))
        self.assertEqual(self.store.lineage_validated(fid)[0], 1)
        self.assertEqual(self.store.run_result(row["run_id"])["status"], "ok")
        self.assertEqual((self.root / row["path"]).read_bytes(), original,
                         "completing the retry retains the interrupted evidence")

    def test_preview_snapshot_is_coherent_and_apply_rechecks_another_connections_change(self):
        fid, _ = self.interrupted()
        other = SwarmStore(self.root, clock=self.clock)
        try:
            read = self.store.run_result
            def concurrent_change(run_id):
                other.update_family(fid, best_version=None)
                return read(run_id)
            with mock.patch.object(self.store, "run_result", side_effect=concurrent_change):
                preview = self.store.repair_interrupted_validation(fid)
            self.assertTrue(preview["eligible"], "the snapshot coherently describes the family before the change")
            self.assertEqual(preview["before"]["best_version"], 1)
            self.assertIsNone(self.store.family(fid)["best_version"])
            self.assert_refused_unchanged(fid)
        finally:
            other.close()

    def test_readonly_preview_is_supported_and_apply_is_refused(self):
        fid, _ = self.interrupted()
        with_store = SwarmStore(self.root, readonly=True)
        try:
            self.assertTrue(with_store.repair_interrupted_validation(fid)["eligible"])
            with self.assertRaisesRegex(ValueError, "readonly"):
                with_store.repair_interrupted_validation(fid, apply=True)
        finally:
            with_store.close()

    def test_counter_history_completed_results_and_retired_or_banded_families_are_refused(self):
        changes = ({"validations": 2}, {"best_validation": 0.0}, {"retired_at": self.store.now()},
                   {"band": "candidate"}, {"band": "probe"}, {"band": "sized"})
        for i, fields in enumerate(changes):
            with self.subTest(fields=fields):
                fid, _ = self.interrupted(f"synthetic-fields-{i}")
                self.store.update_family(fid, **fields)
                self.assert_refused_unchanged(fid)
        for status in ("error", "ok", "disqualified", "no_data"):
            with self.subTest(extra=status):
                fid, _ = self.interrupted(f"synthetic-extra-{status}")
                extra = {"run_id": f"{fid}-extra", "status": status, "trials": 0, "summary": {}}
                self.store.add_run(fid, 1, extra, window="validation", stress=1.0, purpose="validation")
                self.assert_refused_unchanged(fid)

    def test_gate_incubator_live_and_historical_look_activity_is_never_cleared(self):
        fields = ("gate", "gate_ready", "gate_hold", "gate_outcome", "gated_sha", "review", "look_inflight", "look_wait",
                  "unit_wait", "extension_hold", "incubator_reviews", "incubator_barred", "train_passed", "banded_at",
                  "forward", "forward_replay")
        for key in fields:
            with self.subTest(key=key):
                fid, _ = self.interrupted(f"synthetic-protected-{key}")
                self.store.set_state(fid, **{key: {"invented": True}})
                self.assert_refused_unchanged(fid)
        fid, _ = self.interrupted("synthetic-prior-look")
        self.store.add_look(fid, 1, "invented-sha", passed=False, p_value=.9, detail={})
        self.assert_refused_unchanged(fid)
        fid, _ = self.interrupted("synthetic-prior-band")
        self.store.set_band(fid, "candidate", reason="invented")
        self.store.set_band(fid, "gym", reason="invented")
        self.assert_refused_unchanged(fid)

    def test_malformed_state_and_receipts_fail_closed_without_writes(self):
        for i, bad in enumerate((None, [], "bad", [1])):
            with self.subTest(numbers=bad):
                fid, _ = self.interrupted(f"synthetic-bad-numbers-{i}")
                self.store.set_state(fid, validation_numbers=bad)
                self.assert_refused_unchanged(fid)
        fid, _ = self.interrupted("synthetic-bad-state")
        self.store.update_family(fid, state=["bad"])
        self.assert_refused_unchanged(fid)
        for i, raw in enumerate((b"not gzip", gzip.compress(b"{"), gzip.compress(b"[]"))):
            with self.subTest(receipt=i):
                fid, row = self.interrupted(f"synthetic-bad-receipt-{i}")
                (self.root / row["path"]).write_bytes(raw)
                self.assert_refused_unchanged(fid)
        for i, bad in enumerate((False, True, "0", None, {}, [])):
            with self.subTest(trials=bad):
                fid, row = self.interrupted(f"synthetic-bad-trials-{i}")
                payload = self.store.run_result(row["run_id"])
                payload["trials"] = bad
                (self.root / row["path"]).write_bytes(gzip.compress(json.dumps(payload).encode()))
                self.assert_refused_unchanged(fid)
        fid, _ = self.interrupted("synthetic-measured-zero")
        self.store.set_state(fid, validation_numbers={"mean": 0.0})
        self.assert_refused_unchanged(fid)
        fid, _ = self.interrupted("synthetic-bool-marker")
        self.store.set_state(fid, validation_version=True)
        self.assert_refused_unchanged(fid)

    def test_stress_receipt_must_prove_the_same_zero_trial_interruption(self):
        fid, row = self.interrupted(stress=True)
        self.assertTrue(self.store.repair_interrupted_validation(fid)["eligible"])
        stress_row = self.store.run(f"{row['run_id']}-s15")
        for bad in ({"status": "error", "trials": 0, "summary": {"status": "error", "reason": "different"}},
                    {"status": "error", "trials": False, "summary": {"status": "error", "reason": "invented interruption"}},
                    {"status": "error", "trials": 1, "summary": {"status": "error", "reason": "invented interruption"}},
                    {"status": "error", "trials": 0, "gym_image": "other-image",
                     "summary": {"status": "error", "reason": "invented interruption"}}):
            with self.subTest(stress=bad):
                (self.root / stress_row["path"]).write_bytes(gzip.compress(json.dumps(bad).encode()))
                self.assert_refused_unchanged(fid)


if __name__ == "__main__":
    unittest.main()

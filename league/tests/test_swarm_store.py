"""The swarm's store (league/swarm/store.py): families, lineage counts, versions, trials, events, spend."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, result

SPEC = {"id": "condor-vrp", "mechanism": "Index options price more movement than follows: sell a condor.", "structure": "iron_condor",
        "roots": ["spy"], "dte": [0, 2]}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)


class Families(StoreCase):
    def test_a_family_needs_a_known_structure_a_root_and_a_mechanism(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.assertEqual((fam["id"], fam["roots"], fam["band"], fam["lineage"]), ("condor-vrp", ["SPY"], "gym", "condor-vrp"))
        with self.assertRaises(ValueError):
            self.store.add_family({**SPEC, "structure": "naked_put"}, origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family({**SPEC, "roots": []}, origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family({**SPEC, "mechanism": "short"}, origin="seed")

    def test_ids_are_unique_site_slugs(self):
        a = self.store.add_family(SPEC, origin="seed")
        b = self.store.add_family({**SPEC, "id": "Condor VRP!!"}, origin="seed")
        self.assertNotEqual(a["id"], b["id"])
        self.assertRegex(b["id"], r"^[a-z0-9-]{1,40}$")

    def test_a_fork_inherits_the_lineages_trials_and_holdout_looks(self):
        parent = self.store.add_family(SPEC, origin="seed")
        v = self.store.add_version(parent["id"], "code-1", {}, author="seed")
        for i in range(3):
            self.store.add_run(parent["id"], v["n"], result(f"p{i}"), window="train", stress=1.0, purpose="train")
        self.store.add_look(parent["id"], v["n"], "sha-1", passed=False, p_value=0.4, detail={})
        child = self.store.add_family({**SPEC, "id": "condor-vrp-on-qqq", "roots": ["QQQ"]}, origin="fork", parent=parent["id"])
        self.assertEqual((child["lineage"], child["inherited_trials"], child["inherited_looks"]), ("condor-vrp", 3, 1))
        self.store.add_run(child["id"], None, result("c"), window="train", stress=1.0, purpose="train")
        self.assertEqual(self.store.lineage_trials(child["id"]), 4)
        self.assertEqual(self.store.lineage_looks(child["id"]), 1)
        self.assertEqual(len(self.store.lineage_trial_sharpes(child["id"])), 4)

    def test_retire_moves_the_band_and_writes_one_public_event(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.assertTrue(self.store.retire(fam["id"], "no validation improvement in 30 revisions"))
        self.assertFalse(self.store.retire(fam["id"], "again"))
        fam = self.store.family(fam["id"])
        self.assertEqual(fam["band"], "retired")
        kinds = [e["kind"] for e in self.store.events_after(0)]
        self.assertEqual(kinds, ["swarm.retired"])

    def test_band_moves_are_events_and_the_same_band_is_no_move(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.assertEqual(self.store.set_band(fam["id"], "candidate", reason="passed"), "gym")
        self.assertIsNone(self.store.set_band(fam["id"], "candidate", reason="again"))
        [event] = self.store.events_after(0)
        self.assertEqual((event["kind"], event["payload"]["band_from"], event["payload"]["band_to"]), ("swarm.band", "gym", "candidate"))


class Versions(StoreCase):
    def test_versions_live_in_the_state_root_not_in_git_and_dedupe(self):
        fam = self.store.add_family(SPEC, origin="seed")
        v1 = self.store.add_version(fam["id"], "NEEDS = {}\n", {"a": 1}, author="seed")
        again = self.store.add_version(fam["id"], "NEEDS = {}\n", {"a": 1}, author="model")
        v2 = self.store.add_version(fam["id"], "NEEDS = {}\n", {"a": 2}, author="model")
        self.assertEqual((v1["n"], again["n"], v2["n"]), (1, 1, 2))
        self.assertTrue((Path(self.dir.name) / v1["path"]).is_file())
        self.assertTrue(v1["path"].startswith("programs/condor-vrp/"))
        self.assertEqual(self.store.family(fam["id"])["revisions"], 2)
        self.assertEqual(self.store.latest_version(fam["id"])["params"], {"a": 2})


class Runs(StoreCase):
    def test_every_evaluation_is_a_trial_and_a_refusal_is_not(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.store.add_run(fam["id"], 1, result("a"), window="train", stress=1.0, purpose="train", program_years=1.0)
        self.store.add_run(fam["id"], 1, {"status": "refused", "reason": "no", "trials": 0}, window="train", stress=1.0, purpose="train")
        row = self.store.add_run(fam["id"], 1, result("b"), window="validation", stress=1.5, purpose="validation", program_years=1.0)
        self.assertEqual(self.store.family(fam["id"])["trials"], 2)
        self.assertEqual(self.store.totals()["trials"], 2)
        self.assertAlmostEqual(self.store.totals()["market_years"], 2.0)
        full = self.store.run_result(row["run_id"])
        self.assertEqual(len(full["daily"]), 250)

    def test_the_same_run_id_for_another_family_is_kept_apart(self):
        a = self.store.add_family(SPEC, origin="seed")
        b = self.store.add_family({**SPEC, "id": "other"}, origin="seed")
        r = result("x")
        one = self.store.add_run(a["id"], 1, r, window="train", stress=1.0, purpose="train")
        two = self.store.add_run(b["id"], 1, r, window="train", stress=1.0, purpose="train")
        self.assertNotEqual(one["run_id"], two["run_id"])
        self.assertEqual(self.store.add_run(a["id"], 1, r, window="train", stress=1.0, purpose="train")["run_id"], one["run_id"])
        self.assertEqual(self.store.add_run(b["id"], 1, r, window="train", stress=1.0, purpose="train")["run_id"], two["run_id"])
        self.assertEqual(self.store.totals()["trials"], 4, "the same evaluation again is stored once and still counted")
        self.assertEqual((self.store.family(a["id"])["trials"], self.store.family(b["id"])["trials"]), (2, 2))


class Pruning(StoreCase):
    def test_only_the_newest_full_train_results_and_the_best_are_kept(self):
        fam = self.store.add_family(SPEC, origin="seed")
        rows = []
        for i in range(10):
            self.clock.advance(1)
            rows.append(self.store.add_run(fam["id"], i + 1, result(f"r{i}"), window="train", stress=1.0, purpose="train"))
            if i == 1:
                self.store.set_state(fam["id"], best_train_run=rows[-1]["run_id"])
        kept = [r["run_id"] for r in rows if self.store.run_result(r["run_id"]) is not None]
        self.assertEqual(len(kept), SwarmStore.KEEP_FULL_TRAIN_RUNS + 1)
        self.assertIn(rows[1]["run_id"], kept, "the best stays")
        self.assertIsNone(self.store.run_result(rows[0]["run_id"]))
        self.assertEqual(self.store.run(rows[0]["run_id"])["summary"]["trades"], 150, "the summary row stays")
        self.assertEqual(len(list((Path(self.dir.name) / "swarm-runs").iterdir())), SwarmStore.KEEP_FULL_TRAIN_RUNS + 1)
        self.assertEqual(self.store.totals()["trials"], 10, "pruning never lowers a count")


class EventsAndSpend(StoreCase):
    def test_events_are_append_only(self):
        self.store.event("swarm.status", None, {"a": 1})
        with self.assertRaises(sqlite3.DatabaseError):
            self.store._exec("UPDATE events SET kind='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store._exec("DELETE FROM events")

    def test_spend_by_kind_and_since(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.store.add_spend("sail_model", 0.25, family=fam["id"])
        self.clock.advance(7200)
        self.store.add_spend("gym_box", 0.10)
        self.assertAlmostEqual(self.store.spent(["sail_model", "gym_box"]), 0.35)
        self.assertAlmostEqual(self.store.spent(since=self.clock() - 3600), 0.10)
        self.assertAlmostEqual(self.store.family(fam["id"])["spent_usd"], 0.25)

    def test_notebook_graveyard_and_forward(self):
        fam = self.store.add_family(SPEC, origin="seed")
        self.store.note(fam["id"], "condors lose on CPI days")
        self.store.bury(fam["id"], "iron condors on SPY lost on event days", {"t": -1})
        self.assertEqual(self.store.graveyard("condor event")[0]["family"], fam["id"])
        self.assertEqual(self.store.graveyard("zzz"), [])
        n = self.store.add_forward(fam["id"], "shadow", [{"id": "t1", "day": "2026-09-28", "pnl": 5.0, "max_loss": 50.0}] * 2)
        self.assertEqual(n, 1)
        with self.assertRaises(ValueError):
            self.store.add_forward(fam["id"], "dream", [])

    def test_a_readonly_store_cannot_write(self):
        self.store.add_family(SPEC, origin="seed")
        ro = SwarmStore(Path(self.dir.name), readonly=True)
        self.addCleanup(ro.close)
        self.assertEqual(len(ro.families()), 1)
        with self.assertRaises(sqlite3.OperationalError):
            ro.event("swarm.status", None, {})


if __name__ == "__main__":
    unittest.main()

"""The swarm's store (league/swarm/store.py): families, lineage counts, versions, trials, events, spend."""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.swarm.store import SwarmStore, graveyard_words
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

    def test_the_lineage_count_is_every_trial_of_the_lineage(self):
        a = self.store.add_family(SPEC, origin="seed")
        for i in range(10):
            self.store.add_run(a["id"], 1, result(f"a{i}"), window="train", stress=1.0, purpose="train")
        b = self.store.add_family({**SPEC, "id": "b", "roots": ["QQQ"]}, origin="fork", parent=a["id"])
        c = self.store.add_family({**SPEC, "id": "c", "roots": ["IWM"]}, origin="fork", parent=a["id"])
        for i in range(50):
            self.store.add_run(a["id"], 1, result(f"a2{i}"), window="train", stress=1.0, purpose="train")
        for i in range(30):
            self.store.add_run(c["id"], 1, result(f"c{i}"), window="train", stress=1.0, purpose="train")
        counts = {f: self.store.lineage_trials(f) for f in (a["id"], b["id"], c["id"])}
        self.assertEqual(counts, {a["id"]: 90, b["id"]: 90, c["id"]: 90}, "N and the trial Sharpes are the same set")
        self.assertEqual(len(self.store.lineage_trial_sharpes(b["id"])), 90)

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


class GraveyardRanking(StoreCase):
    """`graveyard(query)` ranks by relevance that does not grow with a lesson's length (`rank_graveyard`)."""

    def bury(self, fid: str, mechanism: str, lesson: str, *, structure: str = "debit_vertical", roots=("SPY",),
             advance: float = 60) -> None:
        self.store.add_family({"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots), "dte": [0, 5]},
                              origin="seed")
        self.store.bury(fid, lesson)
        self.clock.advance(advance)

    def ids(self, query: str, limit: int = 8) -> list[str]:
        return [g["family"] for g in self.store.graveyard(query, limit=limit)]

    def test_a_long_repetitive_lesson_no_longer_beats_a_short_exact_match(self):
        self.bury("exact", "Buy a QQQ straddle into earnings: the overnight gap is underpriced convexity.",
                  "Earnings gaps on QQQ were priced fairly; the straddle lost its premium.",
                  structure="long_straddle", roots=["QQQ"])
        notes = "Note: the gap filter fired on earnings day again and the signal decayed before the open. " * 30
        self.bury("verbose", "Sell index premium on quiet days when implied volatility is rich.", notes,
                  structure="iron_condor", roots=["SPY"])
        for i in range(4):
            self.bury(f"filler-{i}", f"Buy calls after a trend day on SPY, variant {i}, following momentum.",
                      "Trend days did not persist past the close.", structure="long_call")
        query = "long_straddle QQQ Buy a straddle into earnings because the overnight gap is underpriced convexity."
        # The old score (raw occurrences) put the repetitive lesson first by a wide margin.
        raw = {g["family"]: sum(f"{g['mechanism']} {g['structure']} {g['roots']} {g['lesson']}".lower().count(w)
                                for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2)
               for g in self.store.graveyard(limit=20)}
        self.assertGreater(raw["verbose"], 3 * raw["exact"])
        self.assertEqual(self.ids(query, limit=3)[0], "exact")

    def test_a_rare_word_outweighs_a_common_one(self):
        for i in range(5):
            self.bury(f"spy-{i}", f"SPY opening drive number {i} continues into the afternoon.", "SPY SPY SPY drifted; SPY faded.")
        self.bury("vix", "When the VIX term structure inverts, index puts are overpriced.", "The inversion signal was too rare.",
                  roots=["XSP"])
        self.assertEqual(self.ids("SPY VIX")[0], "vix")

    def test_a_structure_name_counts_as_one_word(self):
        self.bury("put", "After a flush the rebound is underpriced convexity.", "A call would have done better than this put.",
                  structure="long_put")
        self.bury("call", "After a flush the rebound is underpriced convexity.", "The rebound came too late for weeklies.",
                  structure="long_call")
        self.assertEqual(self.ids("long_call SPY flush rebound convexity"), ["call", "put"])
        self.assertEqual(graveyard_words("long_call SPY"), ["call", "long", "long_call", "spy"])
        self.assertEqual(graveyard_words("iv_rv on SPX"), ["spx"])

    def test_the_filter_is_unchanged_a_row_needs_some_query_word(self):
        self.bury("condors", "Index options price more movement than follows: sell condors.", "Condors died on event days.",
                  structure="iron_condor")
        self.bury("calls", "Buy calls after a trend day on SPY: momentum carries.", "Trend days did not persist.",
                  structure="long_call")
        self.assertEqual(self.ids("condor"), ["condors"])   # a query word as a substring, as before
        self.assertEqual(self.ids("zzz qqq"), [])

    def test_ordering_is_deterministic_ties_go_to_the_newer_row_then_the_id(self):
        mech, lesson = "Buy a butterfly at the pin strike into expiry on SPY.", "The pin did not hold."
        self.bury("tie-b", mech, lesson, advance=0)
        self.bury("tie-a", mech, lesson)
        self.bury("tie-c", mech, lesson)
        first = self.ids("pin strike butterfly expiry")
        self.assertEqual(first, ["tie-c", "tie-a", "tie-b"])
        for _ in range(3):
            self.assertEqual(self.ids("pin strike butterfly expiry"), first)

    def test_the_empty_query_returns_the_newest_first(self):
        for fid in ("oldest", "middle", "newest"):
            self.bury(fid, f"A mechanism for the {fid} family that says why it should pay.", f"The {fid} lesson.")
        self.assertEqual(self.ids(""), ["newest", "middle", "oldest"])
        self.assertEqual(self.ids("a of"), ["newest", "middle", "oldest"])   # no word longer than two letters
        self.assertEqual(self.ids("", limit=2), ["newest", "middle"])
        [row] = self.store.graveyard("newest", limit=1)
        self.assertEqual((row["family"], row["roots"], row["best"]), ("newest", ["SPY"], {}))


if __name__ == "__main__":
    unittest.main()

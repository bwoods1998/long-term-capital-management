"""The incubator's facts from the swarm (`league.swarm.bands.incubator`, release B, Oct 1, 2026): one row, or none, saying
whether a version of an alive Gym-band family may trade the incubator route. Every condition removed alone gives no row;
`bands.read` never returns one; an unreadable store raises (the live path takes no pin and refuses opens)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.swarm import DB_NAME, bands
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

CODE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 3}

def decide(ctx):
    return []
'''
EVALUATOR = {"image": "img-1", "bundle": "bundle-1", "execution": "exec-1"}
OBJECTIVE = {"span": "2017-01-01..2024-12-31"}


class FactsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root, clock=Clock())
        self.addCleanup(self.store.close)
        self.store.put("research_evaluator", EVALUATOR)
        self.store.put("train_objective", OBJECTIVE)
        from league.gym.review_contract import review_contract

        self.contract = review_contract()["sha256"]

    def sha(self, fid: str, n: int = 1) -> str:
        from league.swarm.gate import run_sha

        return run_sha(self.store.version(fid, n))

    def review(self, sha: str, *, verdict="pass", audit="pass", contract=None, audit_contract=None) -> dict:
        return {"sha": sha, "verdict": verdict, "contract_sha": contract or self.contract,
                "audit": {"verdict": audit, "contract_sha": audit_contract or self.contract}}

    def eligible(self, fid: str = "fam", *, structure: str = "debit_vertical", review_in: str = "review") -> str:
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": structure, "roots": ["SPY"],
                               "dte": [0, 5]}, origin="test")
        self.store.add_version(fid, CODE, {"hold": 3}, author="test")
        sha = self.sha(fid)
        state = {"train_passed": {"1": {"evaluator": EVALUATOR, "objective": OBJECTIVE, "run": "r1", "robust_pnl": 12.0,
                                        "drift": {"t": 1.1, "positive": True, "years": 5}, "at": 1.0}}}
        if review_in == "review":
            state["review"] = self.review(sha)
        else:
            state["incubator_reviews"] = {sha: dict(self.review(sha), version=1, model="m", route="r", at=1.0)}
        self.store.set_state(fid, **state)
        return sha

    def row(self, fid="fam", n=1):
        return bands.incubator(self.root, family=fid, version=n)


class TheRow(FactsCase):
    def test_an_eligible_version_has_one_row_with_no_program_and_every_flag_that_keeps_it_off_d2(self):
        sha = self.eligible()
        [row] = self.row()
        self.assertEqual(row, {"family": "fam", "version": 1, "run_sha": sha, "structure": "debit_vertical",
                               "roots": ["SPY"], "band": "gym", "incubator": True, "observe": False,
                               "holdout_passed": False, "validation_passed": False})
        self.assertNotIn("code", row)
        self.assertNotIn("params", row)

    def test_the_incubators_own_review_counts_like_the_gates(self):
        self.eligible(review_in="incubator_reviews")
        self.assertEqual(len(self.row()), 1)

    def test_bands_read_never_returns_it_and_the_lookup_is_by_version(self):
        self.eligible()
        self.assertEqual(bands.read(self.root), [])
        self.assertEqual(self.row(n=2), [], "no such version")
        self.assertEqual(self.row(fid="nobody"), [])
        self.assertEqual(bands.incubator(self.root, family="fam", version=0), [])

    def test_no_store_is_no_row_and_an_unreadable_one_raises(self):
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        self.assertEqual(bands.incubator(empty.name, family="fam", version=1), [])
        bad = Path(empty.name) / DB_NAME
        bad.write_bytes(b"this is not a database at all" * 100)
        with self.assertRaises(sqlite3.Error):
            bands.incubator(empty.name, family="fam", version=1)


class EveryConditionAlone(FactsCase):
    def assertNoRow(self, why: str):
        self.assertEqual(self.row(), [], why)

    def test_retired_or_not_in_the_gym(self):
        self.eligible()
        self.store.retire_gym("fam", "finished", floor=0, source="test")
        self.assertNoRow("retired")
        self.eligible("other")
        self.store.set_band("other", "candidate", reason="test")
        self.assertEqual(self.row("other"), [], "a Candidate is D2's, never the incubator's")

    def test_demoted_at_one_and_a_half_or_by_drift(self):
        self.eligible()
        self.store.set_state("fam", robust_failed=[1])
        self.assertNoRow("lost at 1.5x")
        self.store.set_state("fam", robust_failed=[], drift_failed={"1": {"why": "drift"}})
        self.assertNoRow("failed the drift screen")

    def test_no_train_pass_or_a_stale_one(self):
        self.eligible()
        state = self.store.family("fam")["state"]
        mark = state["train_passed"]["1"]
        self.store.set_state("fam", train_passed={})
        self.assertNoRow("no Train-and-drift pass")
        self.store.set_state("fam", train_passed={"1": dict(mark, evaluator={**EVALUATOR, "bundle": "old"})})
        self.assertNoRow("a mark from another evaluator")
        self.store.set_state("fam", train_passed={"1": dict(mark, objective={"span": "other"})})
        self.assertNoRow("a mark under another Train objective")
        self.store.set_state("fam", train_passed={"1": {k: v for k, v in mark.items() if k != "objective"}})
        self.assertNoRow("a mark without its objective")
        self.store.set_state("fam", train_passed={"2": mark})
        self.assertNoRow("another version's mark")
        self.store.set_state("fam", train_passed={"1": mark})
        self.assertEqual(len(self.row()), 1)
        self.store.put("research_evaluator", None)
        self.assertNoRow("no current evaluator")

    def test_no_review_a_failed_review_or_audit_a_stale_contract_or_another_shas(self):
        sha = self.eligible()
        for review, why in ((None, "no review"), (self.review(sha, verdict="fail"), "a failed review"),
                            (self.review(sha, audit="fail"), "a failed audit"),
                            (self.review(sha, contract="0" * 64), "a stale review contract"),
                            (self.review(sha, audit_contract="0" * 64), "a stale audit contract"),
                            (self.review("another-sha"), "a review of another program")):
            self.store.set_state("fam", review=review)
            self.assertNoRow(why)
        self.store.set_state("fam", review=None, incubator_reviews={sha: self.review(sha, audit="fail")})
        self.assertNoRow("the incubator's own review with a failed audit")
        self.store.set_state("fam", incubator_reviews={"another-sha": self.review("another-sha")})
        self.assertNoRow("the incubator's review of another sha")

    def test_the_gate_refused_failed_or_demoted_it(self):
        sha = self.eligible()
        for result in ("refused", "failed", "demoted"):
            self.store.set_state("fam", gate_outcome={"sha": sha, "result": result})
            self.assertNoRow(result)
        self.store.set_state("fam", gate_outcome={"sha": "another-sha", "result": "refused"})
        self.assertEqual(len(self.row()), 1, "another program's outcome is not this one's")


if __name__ == "__main__":
    unittest.main()

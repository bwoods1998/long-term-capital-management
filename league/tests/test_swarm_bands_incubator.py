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

    def eligible(self, fid: str = "fam", *, structure: str = "debit_vertical", review_in: str = "review",
                 params: dict | None = None) -> str:
        """Version 1 of `fid`, eligible. Every family here holds the same program (the same code and params, so the same
        run_sha) unless `params` gives it another."""
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": structure, "roots": ["SPY"],
                               "dte": [0, 5]}, origin="test")
        self.store.add_version(fid, CODE, params or {"hold": 3}, author="test")
        sha = self.sha(fid)
        state = {"train_passed": {"1": {"evaluator": EVALUATOR, "objective": OBJECTIVE, "run": "r1", "robust_pnl": 12.0,
                                        "drift": {"t": 1.1, "positive": 4, "years": 5}, "at": 1.0}}}
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

    def test_the_marks_own_content_is_a_belt(self):
        """B2 writes only passing marks; this reader still wants a known Train objective, a positive 1.5x Train P&L and
        the drift screen's figures (B2's shape: `positive` is a count of positive years)."""
        self.eligible()
        mark = self.store.family("fam")["state"]["train_passed"]["1"]
        self.store.put("train_objective", None)
        self.store.set_state("fam", train_passed={"1": dict(mark, objective=None)})
        self.assertNoRow("no Train objective in the store, and a mark without one")
        self.store.put("train_objective", OBJECTIVE)
        for pnl in (0.0, -3.0, None, "12"):
            self.store.set_state("fam", train_passed={"1": dict(mark, robust_pnl=pnl)})
            self.assertNoRow(f"robust_pnl {pnl!r}")
        self.store.set_state("fam", train_passed={"1": {k: v for k, v in mark.items() if k != "robust_pnl"}})
        self.assertNoRow("no robust_pnl")
        for drift in (None, "passed", []):
            self.store.set_state("fam", train_passed={"1": dict(mark, drift=drift)})
            self.assertNoRow(f"drift {drift!r}")
        self.store.set_state("fam", train_passed={"1": mark})
        self.assertEqual(len(self.row()), 1)

    def test_a_family_on_the_d2_route_has_no_row_even_when_read_cannot_admit_it(self):
        """A Gym family whose validated version met the validation line is D2's (its tuition row, `:t` > `:i`): no
        incubator row, so a `bands.read` that came back empty for a moment never lets its `:i` trade first."""
        self.eligible()
        self.store.set_state("fam", validation_line={"passed": True}, validation_version=1)
        self.assertNoRow("validated: D2's route")
        self.store.set_state("fam", validation_line={"passed": False})
        self.assertEqual(len(self.row()), 1, "a validation line not met leaves the incubator's route")

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

    def test_the_gate_refused_failed_demoted_or_held_it(self):
        sha = self.eligible()
        for result in ("refused", "failed", "demoted", "held"):  # "held": THE LOOK HOLDS (a held look is a failed one here)
            self.store.set_state("fam", gate_outcome={"sha": sha, "result": result})
            self.assertNoRow(result)
        self.store.set_state("fam", gate_outcome={"sha": "another-sha", "result": "refused"})
        self.assertEqual(len(self.row()), 1, "another program's outcome is not this one's")


class TheBelt(FactsCase):
    """THE READER'S BELT (Oct 1, 2026; the owner's term: a program whose review or audit failed never trades the
    incubator): the reader refuses on the verdicts themselves, whatever the Train-and-drift mark says, before any sweep
    has removed it, and fails closed on records it cannot read."""

    def assertNoRow(self, why: str, fid: str = "fam"):
        self.assertEqual(self.row(fid), [], why)

    def test_p2_a_failed_gate_review_written_straight_into_state_refuses_where_the_incubators_passed(self):
        """The verification's probe p2: the incubator's own review and audit passed, the mark stands, and the gate's
        `review` of the same program says anything but a pass with a passed audit: no row."""
        sha = self.eligible(review_in="incubator_reviews")
        self.assertEqual(len(self.row()), 1)
        contract = self.contract
        for fields, why in (({"verdict": "fail"}, "a failed review"),
                            ({"verdict": "fail", "stage": "audit", "audit": {"verdict": "fail"}}, "a failed audit"),
                            ({"verdict": "pass", "audit": {"verdict": "fail"}}, "a pass whose audit failed"),
                            ({"verdict": "fail", "contract_sha": "0" * 64}, "a failed review under another contract"),
                            ({"verdict": "unclear"}, "an unclear review"),
                            ({"verdict": ["pass"]}, "a verdict that is not a word"),
                            ({}, "no verdict"),
                            ({"verdict": "pass", "audit": {"verdict": "unclear"}}, "an unclear audit"),
                            ({"verdict": "pass", "audit": "pass"}, "an audit that is not a record"),
                            ({"verdict": "pass", "contract_sha": contract}, "a pass whose audit is owed: not final")):
            self.store.set_state("fam", review={"sha": sha, "version": 1, **fields})
            self.assertNoRow(why)
            self.assertIsNotNone(bands.incubator_refusal(self.store.family("fam")["state"], sha), why)
        self.store.set_state("fam", review={"sha": "another-sha", "version": 2, "verdict": "fail"})
        self.assertEqual(len(self.row()), 1, "another program's failed review is not this one's")
        self.store.set_state("fam", review=self.review(sha, contract="0" * 64))
        self.assertEqual(len(self.row()), 1, "a pass and a passed audit under an older contract is no verdict against it")

    def test_a_recorded_bar_refuses_whatever_passed(self):
        sha = self.eligible()
        self.store.set_state("fam", incubator_reviews={sha: dict(self.review(sha), version=1)})
        for entry in ({"why": "the gate's audit failed it", "at": 1.0}, None, "x"):
            self.store.set_state("fam", incubator_barred={sha: entry})
            self.assertNoRow(f"barred ({entry!r}), with both reviews passed")
        self.store.set_state("fam", incubator_barred={"another-sha": {"why": "x"}})
        self.assertEqual(len(self.row()), 1, "another program's bar is not this one's")

    def test_the_incubators_failed_or_revoked_review_refuses_even_where_the_gates_passed(self):
        sha = self.eligible()
        for record, why in ((dict(self.review(sha), verdict="fail"), "its review failed"),
                            (dict(self.review(sha, audit="fail"), verdict="fail", stage="audit"), "its audit failed"),
                            (dict(self.review(sha, audit="fail")), "a pass whose audit failed"),
                            (dict(self.review(sha), verdict="fail", stage="gate"), "revoked (the gate barred it)"),
                            (dict(self.review(sha, contract="0" * 64), verdict="fail"), "failed under another contract"),
                            ({"sha": sha, "verdict": "pass", "audit": None}, "an audit that cannot be read"),
                            ("garbage", "a record that cannot be read"),
                            (dict(self.review("another-sha")), "a record kept under the wrong program")):
            self.store.set_state("fam", incubator_reviews={sha: record})
            self.assertNoRow(why)
        self.store.set_state("fam", incubator_reviews={sha: {"sha": sha, "verdict": "pass", "contract_sha": self.contract}})
        self.assertEqual(len(self.row()), 1, "the incubator's pass whose audit is owed: the gate's passed reading counts")

    def test_a_refused_version_refuses_even_after_every_record_moved_on(self):
        self.eligible()
        self.eligible("other", params={"hold": 4})  # another program
        self.store.refuse("fam", 1, "rations", "the lineage's three holdout looks are spent")
        self.assertNoRow("a refusal row, with no outcome, review or bar naming it")
        self.store.refuse("other", 2, "review", "another version's refusal")
        self.store.refuse("other", None, "rations", "a refusal of no version")
        self.assertEqual(len(self.row("other")), 1, "another program's refusal, or a refusal of no version, is not this one's")

    def test_a_failed_holdout_look_on_the_program_refuses_in_any_family(self):
        sha = self.eligible()
        self.store.add_look("fam", 1, "another-sha", passed=False, p_value=0.9, detail={})
        self.assertEqual(len(self.row()), 1, "another program's failed look")
        self.store.add_look("fam", 1, sha, passed=False, p_value=0.9, detail={})
        self.assertNoRow("a failed holdout look, with no outcome naming it")
        self.eligible("other", review_in="incubator_reviews")
        self.store.set_state("other", review=None)
        self.assertNoRow("the same program failed a look in another family", "other")

    def test_records_that_cannot_be_read_fail_closed(self):
        sha = self.eligible(review_in="incubator_reviews")
        family = self.store.family("fam")
        for key in (*bands.BELT_RECORDS, "train_passed", "validation_line", "drift_failed", "robust_failed"):
            for garbage in ("garbage", 7, ["x"]) if key != "robust_failed" else ("garbage", {"1": True}, 7):
                self.store.update_family("fam", state={**family["state"], key: garbage})
                self.assertNoRow(f"{key}={garbage!r}")
                self.assertIn("cannot be read", bands.incubator_refusal(self.store.family("fam")["state"], sha), key)
        for review in ({"verdict": "fail"}, {"sha": 7, "verdict": "pass"}, {"sha": "", "verdict": "pass"}):
            self.store.update_family("fam", state={**family["state"], "review": review})
            self.assertNoRow(f"a review naming no program: {review!r}")
        for state in (["x"], "x", 7):
            self.store.update_family("fam", state=state)
            self.assertNoRow(f"a state that is not a record: {state!r}")
        self.store.update_family("fam", state={**family["state"], "review": {}})
        self.assertEqual(len(self.row()), 1, "an empty review is no review: the incubator's own pass counts")
        self.store.update_family("fam", state=family["state"])
        self.assertEqual(len(self.row()), 1)


class TheProgram(FactsCase):
    """The round-3 verification's probe Q2: a verdict is on the PROGRAM (the same code and params, the same run_sha), so
    the belt refuses it in every family when any family, alive or retired, holds a refusal of it, a bar, a failed review
    or audit or a bad outcome, or a record that cannot be read; and while the gate owes a bar on it (`BARS_OWED_FILE`)."""

    def setUp(self):
        super().setUp()
        self.sha_ = self.eligible("fam", review_in="incubator_reviews")
        self.assertEqual(self.eligible("twin", review_in="incubator_reviews"), self.sha_, "the same program")
        self.eligible("else", review_in="incubator_reviews", params={"hold": 4})
        self.assertEqual([len(self.row(f)) for f in ("fam", "twin", "else")], [1, 1, 1])
        self.clean = self.store.family("fam")["state"]

    def assertOnlyTwinsRefused(self, why: str):
        self.assertEqual((self.row("fam"), self.row("twin")), ([], []), why)
        self.assertEqual(len(self.row("else")), 1, f"another program is not refused: {why}")

    def test_a_refusal_bar_or_failed_verdict_in_one_family_refuses_the_program_in_every_family(self):
        sha = self.sha_
        for values, why in (({"incubator_barred": {sha: {"why": "the gate's audit failed it"}}}, "a recorded bar"),
                            ({"review": {"sha": sha, "verdict": "fail"}}, "the gate's failed review"),
                            ({"review": self.review(sha, audit="fail")}, "the gate's failed audit"),
                            ({"incubator_reviews": {sha: dict(self.review(sha), verdict="fail")}}, "the incubator's fail"),
                            ({"gate_outcome": {"sha": sha, "result": "demoted"}}, "a bad outcome"),
                            ({"review": "garbled"}, "a review record that cannot be read"),
                            ({"incubator_barred": ["x"]}, "bars that cannot be read")):
            self.store.update_family("fam", state={**self.clean, **values})
            self.assertOnlyTwinsRefused(why)
        self.store.update_family("fam", state="not a record")
        self.assertOnlyTwinsRefused("a state that cannot be read")
        self.store._exec("UPDATE families SET state=? WHERE id=?", ("{not json", "fam"))
        self.assertOnlyTwinsRefused("a state that is not JSON")
        self.store.update_family("fam", state=self.clean)
        self.assertEqual(len(self.row("twin")), 1)

    def test_a_refusal_of_the_program_in_a_retired_family_refuses_it(self):
        self.store.retire_gym("fam", "finished", floor=0, source="test")
        self.assertEqual(len(self.row("twin")), 1, "retiring is no verdict")
        self.store.refuse("fam", 1, "review", "the gate's reviewer failed it")
        self.assertEqual(self.row("twin"), [], "a refusal of the same program, in a retired family")
        self.assertEqual(len(self.row("else")), 1)

    def test_a_bar_the_gate_owes_refuses_the_program_and_an_unreadable_record_of_them_refuses_every_program(self):
        path = self.root / bands.BARS_OWED_FILE
        path.write_text('{"bars": [{"family": "fam", "sha": "%s", "version": 1, "why": "x"}]}' % self.sha_)
        self.assertOnlyTwinsRefused("a bar owed")
        path.write_text('{"bars": [{"family": "fam", "sha": "another", "version": 1, "why": "x"}]}')
        self.assertEqual(len(self.row("twin")), 1, "another program's owed bar")
        for garbage in ("{not json", '{"bars": "x"}', '{"bars": [{"sha": 7}]}', "[]"):
            path.write_text(garbage)
            self.assertEqual([self.row(f) for f in ("fam", "twin", "else")], [[], [], []], f"fail-closed: {garbage!r}")
        path.unlink()
        self.assertEqual(len(self.row("else")), 1)


if __name__ == "__main__":
    unittest.main()

"""THE PROGRAM BAR ON THE LOOK ROUTE (release F1, Oct 3, 2026; `league/swarm/gate.py` `Gate.program_bar`,
`league/swarm/incubator.py` `look_route_bar`).

With the held-out look the route to Probe, the gate's review and audit are the only screen against a program that
recognises the held-out months. Their verdict used to be read by the family and version it was made in, so the same
code and parameters in a revived or twin family, or in its own family after a new Gym cleared the gate's mark, was read
and looked at afresh. Now a program with a failed review, a failed audit or a refusal on record anywhere is never read
again and never looked at, whatever family or version carries it now: refused before anything is paid, and again under
the lock in `look()`, and a third time before a pass is banded; and `Tournament.gate_spent` never readies a refused
version again (`allocation.gate_spent` agrees). A hold is no bar (the look hold judges the program again), nor is the
"gym" refusal (no one judged it), nor the sweep's revocation of a passed incubator review, which an adoption records
as a bar. A holder's record that cannot be read is waited on: nothing refused, nothing read. Every figure is
invented."""

from __future__ import annotations

import json
import re
import unittest

from league.swarm import allocation, bands, evaluator, incubator
from league.swarm.gate import (HOLD_DRIFT_STAGE, HOLD_OUTCOME, PROGRAM_BAR_STAGE, PROGRAM_BAR_WORDS, Gate, run_sha)
from league.swarm.tournament import Tournament
from league.tests.evaluator_fakes import reviewed
from league.tests.swarm_fakes import FakeFrontier, drift_block, result
from league.tests.test_swarm_rounds import SPEC, RoundCase, review_failure, strong, stronger

CODE = "# one program\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
FAIL = {"text": json.dumps(review_failure("calendar recognition"))}


class BarCase(RoundCase):
    """Families that hold the very same program (`holder`: the same code and params, the same run sha), validated by the
    real tournament and taken to the real gate."""

    def holder(self, fid: str, code: str = CODE) -> str:
        self.store.add_family({**SPEC, "id": fid}, origin="seed")
        v = self.store.add_version(fid, code, {}, author="seed")
        self.store.update_family(fid, best_version=v["n"])
        return run_sha(self.store.version(fid, v["n"]))

    def validate(self, *fids: str) -> dict:
        """The tournament's validation of the living families (or of `fids` alone). The same code in several families is
        one lineage, and each validated version raises the deflated Sharpe's bar for the next: a third holder's
        validation answers `stronger`."""
        fams = [self.store.family(f) for f in fids] if fids else self.store.families(alive=True)
        out = Tournament(self.store, self.pool, self.settings).validate(fams)
        for fid in fids:
            self.assertTrue(self.state(fid)["gate_ready"], f"{fid}: validated and at the gate")
        return out

    def validate_own(self, fid: str) -> dict:
        """A THIRD holder of the program, validated by its own job. The lineage then counts three validated versions,
        and this fixture's Gym answers `stronger` for the third so that it meets the line at that count: an answer no
        Gym gives the same program twice. AN IDENTICAL PROGRAM IS VALIDATED ONCE (release F1's research stream,
        `Tournament.known_validation`) rightly reads the earlier holders' stored result instead, which fails at that
        count, and inherits the failure: the third holder would never reach the gate. What the gate does with a
        program that reaches it is this module's subject, so that rule is off for this one step (its own tests:
        `test_swarm_f1_research.ValidatedOnce`); a second holder is validated with it on, as shipped (a result that
        meets the line is never inherited)."""
        kept = self.settings["tournament"].get("reuse_validations", True)
        self.settings["tournament"]["reuse_validations"] = False
        try:
            return self.validate(fid)
        finally:
            self.settings["tournament"]["reuse_validations"] = kept

    def gate(self) -> Gate:
        self.clock.advance(600)
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def state(self, fid: str) -> dict:
        return self.store.family(fid)["state"]

    def reads(self) -> int:
        """Model reads made so far: Sail's bodies and the gateway's frontier asks."""
        return len(self.sail.bodies) + len(self.asked)

    def holdout_jobs(self) -> list:
        return [j for j in self.pool.jobs if j.window == "holdout"]

    def stages(self, fid: str | None = None) -> list[tuple[str, str]]:
        return [(r["family"], r["stage"]) for r in self.store.refusals(fid)]

    def failed_in(self, fid: str = "a", reply: dict = FAIL) -> str:
        """`fid`'s program, validated, and failed by the gate's reviewer: the refusal row, the bar. Its run sha."""
        sha = self.holder(fid)
        self.validate()
        self.assertTrue(self.state(fid)["gate_ready"])
        self.replies = [reply]
        self.assertEqual(self.gate().run()["refused"], [fid])
        self.assertEqual(self.stages(), [(fid, "review")])
        self.assertEqual(self.state(fid)["incubator_barred"][sha]["why"], "the gate's reviewer failed it")
        return sha

    def assert_refused_unread(self, fid: str, sha: str, bar: str, *, reads: int, out: dict) -> None:
        """Refused at the program bar: nothing paid, nothing opened, the Gym band, the row with the researcher's words,
        the gate's place closed, and the earlier verdict in the private event alone."""
        self.assertEqual((out["refused"], out["looked"], out["look_held"]), ([fid], [], []))
        self.assertEqual((self.reads() - reads, self.holdout_jobs(), self.store.looks()), (0, [], []),
                         "no review, no audit, no sealed read, no look row")
        fam = self.store.family(fid)
        state = fam["state"]
        self.assertEqual((fam["band"], bands.read(self.root)), ("gym", []))
        [row] = self.store.refusals(fid)
        self.assertEqual((row["stage"], row["reason"]), (PROGRAM_BAR_STAGE, PROGRAM_BAR_WORDS))
        self.assertEqual((state["gated_sha"], state["gate_ready"], state["gate_outcome"]["result"], state.get("review")),
                         (sha, False, "refused", None))
        self.assertEqual(state["gate"], f"fail (the {PROGRAM_BAR_STAGE}: {PROGRAM_BAR_WORDS})")
        [event] = [e for e in self.store.events_after(0) if e["payload"].get("action") == "program_bar"
                   and e["family"] == fid]
        self.assertEqual((event["payload"]["bar"], event["payload"]["sha"]), (bar, sha[:12]))
        self.assertEqual(self.store.lineage_looks(fid, include_inflight=True), 0, "no look spent or reserved")


class AFailedReviewIsOnTheProgram(BarCase):
    def test_a_program_the_review_failed_is_refused_unread_in_another_family(self):
        """The statistician's probe, case 1. Before F1: two reads were paid again, one look was made, and the twin
        became a Candidate."""
        sha = self.failed_in("a")
        self.assertEqual(self.holder("b"), sha, "a revive, a fork, a twin: the same code and params")
        self.validate()
        self.assertTrue(self.state("b")["gate_ready"], "readied once: the gate itself says why it will not look")
        reads = self.reads()
        self.replies = [PASS, PASS]  # a second reading would pass it: none is made
        out = self.gate().run()
        self.assert_refused_unread("b", sha, "the gate refused it in a@1 (the review)", reads=reads, out=out)
        # And never again: validated again, it is not made gate-ready, and the next rounds ask nothing.
        self.assertTrue(Tournament(self.store, self.pool, self.settings).gate_spent("b", 1, self.state("b")))
        for _ in range(3):
            self.assertEqual(self.gate().run()["refused"], [])
        self.assertEqual((self.reads() - reads, self.holdout_jobs(), len(self.store.refusals("b"))), (0, [], 1))

    def test_a_failed_audit_bars_it_too(self):
        sha = self.holder("a")
        self.validate()
        self.replies = [PASS, FAIL]
        self.assertEqual(self.gate().run()["refused"], ["a"])
        self.assertEqual(self.stages(), [("a", "audit")])
        self.holder("b")
        self.validate()
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assert_refused_unread("b", sha, "the gate refused it in a@1 (the audit)", reads=reads, out=out)

    def test_a_retired_familys_verdict_still_bars_its_program(self):
        sha = self.failed_in("a")
        self.store.retire("a", "done")
        self.holder("revived")
        self.validate()
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assert_refused_unread("revived", sha, "the gate refused it in a@1 (the review)", reads=reads, out=out)

    def test_the_bar_is_on_the_same_code_and_parameters_to_the_byte(self):
        """THE SAME PROGRAM is the same code and parameters (`run_sha`). Any other text is another program to the bar,
        a copy with one comment added too: both readers read it, as they read any new version, and their verdict on
        it is its own. (The researcher's contract says the same: the bar is on the same code and parameters.)"""
        sha = self.failed_in("a")
        other = self.holder("b", CODE + "# one comment more\n")
        self.assertNotEqual(other, sha)
        self.validate()
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, other))
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual((out["looked"], self.reads() - reads, self.stages("b")), ([{"family": "b", "passed": True}], 2, []))


class GymCase(BarCase):
    """A store that has adopted an evaluator, on a pool that names its Gym: what a release's adoption reads."""

    def setUp(self):
        super().setUp()
        self.gym = {"image": "img", "bundle": "gym-engine-4-aaaa"}
        self.pool.image = lambda kind="gym": "sbcp_gate" if kind == "gate" else self.gym["image"]
        self.pool.bundle = lambda: self.gym["bundle"]
        self.on_gym(strong)
        evaluator.adopt(self.store, evaluator.identity(self.gym["image"], self.gym["bundle"]))

    def on_gym(self, answer) -> None:
        """The Gym's answers from here on: `answer`'s, naming the image and bundle in force."""
        self.answer = lambda job: {**answer(job), "gym_bundle": self.gym["bundle"],
                                   "gym_image": "sbcp_gate" if job.window == "holdout" else self.gym["image"]}

    def train_run(self, fid: str, name: str, *, drift: dict | None = None) -> None:
        """An eligible Train run of version 1 on the Gym in force, as the family's best (what its researcher's run makes).
        `drift`: its drift fit, in place of the fake's (which leans on no drift)."""
        row = result(name, window="train")
        row.update(gym_image=self.gym["image"], gym_bundle=self.gym["bundle"], trials=0, **({"drift": drift} if drift else {}))
        row["summary"]["train_eligible"] = True
        kept = self.store.add_run(fid, 1, row, window="train", stress=1.0, purpose="train")
        self.store.update_family(fid, best_train=1.2, best_version=1)
        self.store.set_state(fid, best_train_run=kept["run_id"], best_train_version=1)

    def paid(self, *verdicts: dict) -> None:
        answers = iter(json.dumps(v) for v in verdicts)
        self.router.frontier_factory = lambda model: FakeFrontier(model, text=next(answers), asked=self.asked)

    def new_gym(self) -> None:
        self.gym["bundle"] = "gym-engine-4-bbbb"
        self.assertTrue(evaluator.adopt(self.store, evaluator.identity(self.gym["image"], self.gym["bundle"]))["gym_changed"])

    def new_live(self) -> None:
        """A release that changes league/live alone: the same Gym, another execution fingerprint."""
        out = evaluator.adopt(self.store, {**dict(self.store.get(evaluator.KEY)), "execution": "another league/live"})
        self.assertEqual((out["adopted"], out["gym_changed"]), (True, False))


class AfterANewGym(GymCase):
    """The probe's case 2, on a PAID route (the OpenAI month has room, so each read would be bought through the
    gateway). A release that changes the Gym clears the selection, the gate's `review` and its mark (`gated_sha`);
    before F1 the family's own failed program was then read again and looked at."""

    def setUp(self):
        super().setUp()
        self.month.value = 100  # the plan's paid readers have room

    def test_the_failed_program_is_never_readied_or_read_again_in_its_own_family(self):
        sha = self.holder("a")
        self.train_run("a", "train-on-aaaa")
        self.validate()
        self.paid(review_failure("calendar recognition"))
        self.assertEqual(self.gate().run()["refused"], ["a"])
        self.assertEqual(([a["model"] for a in self.asked], self.stages()), (["gpt-6-sol"], [("a", "review")]))

        self.new_gym()
        state = self.state("a")
        self.assertEqual((state.get("gated_sha"), state.get("review"), sha in state["incubator_barred"]), (None, None, True),
                         "the gate's mark and its review went with the old Gym; the bar and the refusal row are for good")
        self.train_run("a", "train-on-bbbb")     # its researcher runs the prior program again and submits it
        judged = self.validate()["judged"]["a"]
        self.assertEqual((judged["passed"], self.state("a")["gate_ready"]), (True, False),
                         "it met the line again, and is not made gate-ready: the gate refused this very version")
        fam = self.store.family("a")
        self.assertEqual((Tournament(self.store, self.pool, self.settings).gate_spent("a", 1, fam["state"]),
                          allocation.gate_spent(self.store, fam), fam["state"].get("gated_sha")), (True, True, None),
                         "the rule's two readers agree with no mark left: its Validation t is not counted as alive")
        asked = len(self.asked)
        self.paid({"verdict": "pass"}, {"verdict": "pass"})  # both paid readers would pass it now: neither is asked
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"], len(self.asked) - asked, self.sail.bodies), ([], [], 0, []))
        self.assertEqual((self.holdout_jobs(), self.store.looks(), self.store.family("a")["band"]), ([], [], "gym"))
        self.assertEqual(self.stages(), [("a", "review")], "its one refusal: nothing new is written for it")
        self.assertIn("calendar recognition", self.state("a")["gate"], "and the researcher still reads why")

    def test_were_it_at_the_gate_all_the_same_it_is_refused_before_anything_is_paid(self):
        """The gate's own check does not rest on the tournament's: a barred version that is gate-ready (readied before
        this release, or by hand) is refused at the bar with no paid read."""
        sha = self.holder("a")
        self.train_run("a", "train-on-aaaa")
        self.validate()
        self.paid({"verdict": "pass"}, review_failure("an absolute price level"))
        self.assertEqual(self.gate().run()["refused"], ["a"])
        self.assertEqual(self.stages(), [("a", "audit")])
        self.new_gym()
        self.train_run("a", "train-on-bbbb")
        self.validate()
        self.store.set_state("a", gate_ready=True)
        asked = len(self.asked)
        self.paid({"verdict": "pass"}, {"verdict": "pass"})
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"], len(self.asked) - asked), (["a"], [], 0))
        self.assertEqual(self.stages(), [("a", "audit"), ("a", PROGRAM_BAR_STAGE)])
        self.assertEqual((self.holdout_jobs(), self.store.looks(), self.state("a")["gated_sha"]), ([], [], sha))


class TheVerdictsItReads(BarCase):
    def test_a_refusal_at_any_stage_but_the_gym_bars_the_program(self):
        sha = self.holder("a")
        self.holder("b")
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha))
        self.store.refuse("a", 1, "gym", "the gate box could not make this holdout look three times")
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha), "no one judged the program")
        self.assertFalse(incubator.refused_version(self.store, "a", 1))
        for stage in ("experiment contract", "drift screen", "rations", "duplicate look", "review", "audit",
                      PROGRAM_BAR_STAGE):
            with self.subTest(stage):
                self.store._exec("DELETE FROM refusals WHERE stage != 'gym'")
                self.store.refuse("a", 1, stage, "a synthetic refusal")
                self.assertEqual(incubator.look_route_bar(self.store, "b", 1, sha), f"the gate refused it in a@1 (the {stage})")
                self.assertEqual(incubator.look_route_bar(self.store, "a", 1, sha), f"the gate refused it in a@1 (the {stage})")
                self.assertTrue(incubator.refused_version(self.store, "a", 1))
                self.assertFalse(incubator.refused_version(self.store, "b", 1), "its own row only: b is readied once")

    def test_a_failed_review_whose_write_back_lost_is_still_on_record(self):
        """THE VERDICT FIRST: the gate's compare-and-set lost to a newer validation, so no refusal row and no `review`
        holds the fail; the bar does, and the look route reads it, in the family it was made in and in any other."""
        sha = self.holder("a")
        incubator.record_bar(self.store, "a", sha, "the gate's reviewer failed it", version=1, clock=self.clock)
        self.assertEqual(self.store.refusals(), [])
        self.assertEqual(incubator.look_route_bar(self.store, "a", 1, sha), "the gate's reviewer failed it")
        self.holder("b")
        self.validate("b")
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assert_refused_unread("b", sha, "the gate's reviewer failed it (in a, which holds the same program)",
                                   reads=reads, out=out)
        # In its own family: validated again, it is refused at the bar there too.
        self.validate("a")
        out = self.gate().run()
        self.assertEqual((out["refused"], self.reads() - reads, self.stages("a")), (["a"], 0, [("a", PROGRAM_BAR_STAGE)]))

    def test_the_records_one_family_holds(self):
        sha = "s" * 64
        failed = {"sha": sha, "verdict": "fail", "reasons": ["x"]}
        audit_failed = {"sha": sha, "verdict": "pass", "audit": {"verdict": "fail"}}
        for state, why in (
                ({"incubator_barred": {sha: {"why": "the incubator's audit failed it"}}}, "the incubator's audit failed it"),
                ({"incubator_barred": {sha: "not a mapping"}}, "the gate barred it"),
                ({"review": failed}, "the gate's reviewer failed it"),
                ({"review": {**audit_failed, "verdict": "fail", "stage": "audit"}}, "the gate's audit failed it"),
                ({"incubator_reviews": {sha: failed}}, "the incubator's reviewer failed it"),
                ({"incubator_reviews": {sha: audit_failed}}, "the incubator's audit failed it"),
                ({"gate_outcome": {"sha": sha, "result": "refused"}}, "the gate's outcome for it is refused"),
                ({"incubator_barred": {sha: {"why": "the gate's outcome for it was failed"}}},
                 "the gate's outcome for it was failed")):
            with self.subTest(why):
                self.assertEqual(incubator.state_verdict(state, sha), why)
        for state in ({}, {"review": {"sha": sha, "verdict": "pass"}},                    # its audit still owed
                      {"review": {"sha": sha, "verdict": "pass", "audit": {"verdict": "pass"}}},
                      {"review": {**failed, "sha": "another"}}, {"gate_outcome": {"sha": sha, "result": "waiting"}},
                      {"incubator_reviews": {sha: {"sha": sha, "verdict": "pass", "audit": {"verdict": "pass"}}}},
                      # A held look, in every shape it is recorded: the hold judges the program again.
                      {"gate_outcome": {"sha": sha, "result": HOLD_OUTCOME}},
                      {"incubator_barred": {sha: {"why": f"the gate held its holdout look ({HOLD_DRIFT_STAGE})"}}},
                      {"incubator_barred": {sha: {"why": "the gate's outcome for it was held"}}},
                      {"incubator_barred": {sha: {"why": "the gate refused it (the gym)"}}},
                      # The sweep's revocation of a passed incubator review, for a held program: no verdict of its own.
                      {"incubator_barred": {sha: {"why": "the gate's outcome for it was held"}},
                       "incubator_reviews": {sha: {**failed, "stage": "gate"}}}):
            with self.subTest(state=state):
                self.assertIsNone(incubator.state_verdict(state, sha))

    def test_a_verdict_takes_the_place_of_a_holds_entry_and_never_the_other_way(self):
        """`incubator.record_bar` keeps a program's first entry, except that a verdict is never hidden behind a hold."""
        sha = self.holder("a")
        held = f"the gate held its holdout look ({HOLD_DRIFT_STAGE})"
        incubator.record_bar(self.store, "a", sha, held, version=1, clock=self.clock)
        self.assertIsNone(incubator.look_route_bar(self.store, "a", 1, sha))
        incubator.record_bar(self.store, "a", sha, "the gate's outcome for it was held", clock=self.clock)
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"], held, "a hold's first entry is kept")
        self.clock.advance(60)
        incubator.record_bar(self.store, "a", sha, "the gate's audit failed it", version=1, clock=self.clock)
        entry = self.state("a")["incubator_barred"][sha]
        self.assertEqual((entry["why"], entry["was"]["why"]), ("the gate's audit failed it", held))
        self.assertEqual(incubator.look_route_bar(self.store, "a", 1, sha), "the gate's audit failed it")
        for later in (held, "the gate's reviewer failed it"):
            incubator.record_bar(self.store, "a", sha, later, clock=self.clock)
        self.assertEqual(self.state("a")["incubator_barred"][sha], entry, "a verdict's entry is kept for good")
        self.assertIsNotNone(bands.program_refusal(self.state("a"), sha), "and the incubator's reader refuses it either way")

    def test_a_verdict_the_gate_still_owes_the_store_bars_it(self):
        sha = self.holder("a")
        self.validate()
        gate = self.gate()
        self.assertIsNone(gate.program_bar(self.store.family("a"), 1, sha))
        gate.bars_owed[("elsewhere", sha)] = (1, "the gate's audit failed it")
        self.assertEqual(gate.program_bar(self.store.family("a"), 1, sha), "the gate's audit failed it")
        gate.bars_owed[("elsewhere", sha)] = (1, f"the gate held its holdout look ({HOLD_DRIFT_STAGE})")
        self.assertIsNone(gate.program_bar(self.store.family("a"), 1, sha), "a hold owed is no verdict")

    def test_a_revocation_is_no_verdict_of_its_own(self):
        """The sweep's revocation of a passed incubator review, as an adoption records it (`adoption_bars`): the
        verdict it was revoked for, if there is one, is read where it was made."""
        sha = "s" * 64
        for whose in ("the incubator's", "the gate's"):
            words = f"{whose} {incubator.REVOKED_WORDS}"
            self.assertFalse(incubator.verdict_words(words))
            self.assertIsNone(incubator.state_verdict({"incubator_barred": {sha: {"why": words}}}, sha))
        revoked = {"sha": sha, "verdict": "fail", "stage": "gate", "reasons": ["the gate's outcome for it is held (in a)"]}
        self.assertEqual(incubator.adoption_bars({"incubator_reviews": {sha: revoked}}),
                         {sha: f"the incubator's {incubator.REVOKED_WORDS}"}, "the words an adoption records")
        for verdict in ("the incubator's reviewer failed it", "the gate's audit failed it", "the gate refused it (the review)",
                        "the gate's outcome for it was failed", "the gate's review of it cannot be read", None, 7):
            self.assertTrue(incubator.verdict_words(verdict), verdict)

    def test_a_record_that_cannot_be_read_is_waited_on_and_never_refused_on(self):
        """A holder's record that cannot be read may hold the program's only verdict (here the incubator's failed
        audit, which no refusal row carries). Nothing is refused on it, and nothing is read past it: the version waits
        at the gate, unread and unlooked at, with one alert, until the record reads again."""
        sha = self.holder("a")
        incubator.record_bar(self.store, "a", sha, "the incubator's audit failed it", version=1, clock=self.clock)
        self.holder("b")
        self.validate("b")
        self.assertIsNotNone(incubator.look_route_bar(self.store, "b", 1, sha))
        good = self.store._one("SELECT state FROM families WHERE id='a'")["state"]
        damage = {
            "the state of a, which holds the same program, cannot be read":
                lambda: self.store._exec("UPDATE families SET state=? WHERE id=?", ("not json", "a")),
            "the recorded bars cannot be read (in a, which holds the same program)":
                lambda: self.store.set_state("a", incubator_barred="garbled"),
            "the incubator's reviews cannot be read (in a, which holds the same program)":
                lambda: self.store.set_state("a", incubator_barred=None, incubator_reviews=["garbled"]),
            "the gate's review record cannot be read (in a, which holds the same program)":
                lambda: self.store.set_state("a", incubator_barred=None, review="garbled"),
        }
        reads = self.reads()
        self.replies = [PASS, PASS]  # both readers would pass it: neither is asked
        for why, harm in damage.items():
            with self.subTest(why):
                self.store._exec("UPDATE families SET state=? WHERE id=?", (good, "a"))
                harm()
                self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha),
                                  "a refusal is for good: never on an unread record")
                self.assertEqual(incubator.look_route_unread(self.store, "b", 1), why)
                gate = self.gate()
                for _ in range(2):
                    out = gate.run()
                    self.assertEqual((out["waiting"], out["refused"], out["looked"], out["look_held"]), (["b"], [], [], []))
                self.assertIsNone(gate.look(self.store.family("b"), self.store.version("b", 1), sha), "nor under the lock")
                state = self.state("b")
                self.assertEqual((self.reads() - reads, self.holdout_jobs(), self.store.looks(), self.store.refusals()),
                                 (0, [], [], []), "no review, no audit, no sealed read, no look row, no refusal row")
                self.assertEqual((state["gate_ready"], state.get("gated_sha"), state.get("look_inflight"),
                                  self.store.family("b")["band"]), (True, None, None, "gym"), "its gate place is kept")
                alerts = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                          and e["payload"].get("action") == "program_bar_unread" and e["payload"]["why"] == why]
                self.assertEqual([(a["alert"], a["version"], a["sha"]) for a in alerts], [(True, 1, sha[:12])],
                                 "one alert for the program and the reason, never one a round")
        # Still unread a day on: said again, once.
        self.clock.advance(86400)
        gate = self.gate()
        for _ in range(2):
            self.assertEqual(gate.run()["waiting"], ["b"])
        self.assertEqual(len([e for e in self.store.events_after(0) if e["payload"].get("action") == "program_bar_unread"
                              and e["payload"]["why"] == why]), 2)
        # The record reads again: the verdict it held refuses the program, unread.
        self.store._exec("UPDATE families SET state=? WHERE id=?", (good, "a"))
        self.assertIsNone(incubator.look_route_unread(self.store, "b", 1))
        out = self.gate().run()
        self.assert_refused_unread("b", sha, "the incubator's audit failed it (in a, which holds the same program)",
                                   reads=reads, out=out)

    def test_the_rows_still_speak_beside_a_record_that_cannot_be_read(self):
        """A verdict that CAN be read refuses first: the refusal rows are for good, whatever a holder's state says."""
        sha = self.holder("a")
        self.holder("b")
        self.validate("b")
        self.store._exec("UPDATE families SET state=? WHERE id=?", ("not json", "a"))
        self.store.refuse("a", 1, "review", "a synthetic refusal")
        self.assertEqual(incubator.look_route_bar(self.store, "b", 1, sha), "the gate refused it in a@1 (the review)")
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assert_refused_unread("b", sha, "the gate refused it in a@1 (the review)", reads=reads, out=out)

    def test_the_familys_own_record_that_cannot_be_read_is_waited_on_too(self):
        sha = self.holder("a")
        self.validate("a")
        self.store.set_state("a", incubator_barred="garbled")
        self.assertEqual(incubator.look_route_unread(self.store, "a", 1), "the recorded bars cannot be read")
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual((out["waiting"], out["refused"], out["looked"], self.reads() - reads, self.holdout_jobs()),
                         (["a"], [], [], 0, []))
        self.store.set_state("a", incubator_barred=None)
        self.assertEqual(self.gate().run()["looked"], [{"family": "a", "passed": True}], "it reads again: read and looked at")
        self.assertEqual(self.state("a")["gated_sha"], sha)

    def test_the_researcher_reads_no_figure_and_no_other_familys_name(self):
        self.assertIsNone(re.search(r"\d", PROGRAM_BAR_WORDS), "D2a: no figure")
        self.failed_in("a")
        self.holder("b")
        self.validate()
        self.replies = [PASS, PASS]
        self.gate().run()
        told = self.state("b")["gate"]
        self.assertIn("refused before", told)
        for hidden in ("a@1", "review", "calendar recognition", "(in a"):
            self.assertNotIn(hidden, told.replace("the review, the audit or the gate", ""))


class AHoldIsNoBar(BarCase):
    def test_a_held_program_is_judged_again_by_the_look_holds_not_refused_at_the_bar(self):
        """A look hold closes the version (its row, its incubator bar, the outcome "held") and is no verdict on the
        program: in another family the look hold judges it again, and with the holds off it is read and looked at."""
        sha = self.holder("a")
        self.validate()
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}   # no Train drift fit: held
        # The gate's own hold on a version that reaches it is what is pinned here. With the holds on, GATE-READY AT
        # TRAIN (release F1's research stream) would keep a version with no drift fit from validation in the first
        # place (`test_swarm_f1_gate_ready`: the screen and the gate's hold never disagree), so its screen is off.
        self.settings["researcher"]["carrier_screen"] = False
        self.assertEqual(self.gate().run()["look_held"], ["a"])
        state = self.state("a")
        self.assertEqual((state["gate_outcome"]["result"], state["incubator_barred"][sha]["why"], self.store.refusals()),
                         (HOLD_OUTCOME, f"the gate held its holdout look ({HOLD_DRIFT_STAGE})", []))
        self.holder("b")
        self.validate()
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha))
        out = self.gate().run()
        self.assertEqual((out["look_held"], out["refused"]), (["b"], []), "judged again, and held again")
        self.holder("c")
        self.answer = stronger
        self.validate_own("c")
        self.settings["gate"]["look_holds"] = None
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual((out["looked"], out["refused"]), ([{"family": "c", "passed": True}], []))
        self.assertIsNotNone(incubator.gate_bar(self.store, self.store.family("b"), 1, sha=sha), "the incubator's bar stands")

    def test_the_gym_refusal_is_no_bar_and_its_tries_still_park_the_program(self):
        """Three failed tries write the "gym" refusal: the gate box's failure, not a verdict. In a revived family the
        program still gets its look; a fourth failure parks it at once, with the alert, as before."""
        sha = self.holder("a")
        self.validate()
        self.pool.fail.add("a")
        self.replies = [PASS, PASS]
        for _ in range(3):
            self.gate().run()
        self.assertEqual(self.stages(), [("a", "gym")])
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"], "the gate refused it (the gym)")
        self.store.retire("a", "done")
        self.holder("b")
        self.validate()
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha))
        self.pool.fail.add("b")
        self.replies = [PASS, PASS]
        self.gate().run()
        [alert] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                   and e["payload"].get("action") == "look_failed_three_times" and e["family"] == "b"]
        self.assertEqual((alert["tries"], self.state("b")["gated_sha"], self.stages("b")), (4, sha, []))
        # The gate fixed and the count reset (the operator's step): the program gets its one look.
        self.holder("c")
        self.answer = stronger
        self.validate_own("c")
        self.store.put(f"look_tries:{sha}", 0)
        self.replies = [PASS, PASS]
        self.assertEqual(self.gate().run()["looked"], [{"family": "c", "passed": True}])


class AHoldIsNoBarAcrossAnAdoption(GymCase):
    """A hold in one family, a passed incubator review of the same program in another, then a release. The sweep revokes
    that review for the hold (the incubator's business: a held program never trades it), and the adoption records the
    revoked review as a bar in the twin's state. Read as a verdict, those words barred the program on the look route
    for good, in every family, though no reader had judged it. They are none: only what the gate's own rounds, their
    sweep and `evaluator.adopt` write is on record here."""

    def twin_with_a_passed_incubator_review(self, sha: str) -> None:
        self.assertEqual(self.holder("b"), sha, "the same code and params")
        self.store.set_state("b", incubator_reviews={sha: {**reviewed(sha), "version": 1}})

    def revoked_then_adopted(self, sha: str, why: str, adopt) -> None:
        """The round's sweep revokes b's review for `why`; the adoption records it; no bar follows on the look route."""
        self.gate().run()
        revoked = self.state("b")["incubator_reviews"][sha]
        self.assertEqual((revoked["verdict"], revoked["stage"], revoked["reasons"]), ("fail", "gate", [why]))
        self.assertIsNone(incubator.look_route_bar(self.store, "b", 1, sha), "before the adoption")
        adopt()
        self.assertEqual(self.state("b")["incubator_barred"][sha]["why"], f"the incubator's {incubator.REVOKED_WORDS}",
                         "the adoption recorded the revoked review")
        for fid in ("a", "b"):
            self.assertIsNone(incubator.look_route_bar(self.store, fid, 1, sha), f"{fid}: nothing but a hold is on record")
        self.assertIsNotNone(incubator.gate_bar(self.store, self.store.family("b"), 1, sha=sha), "the incubator's bar stands")

    def held(self, adopt) -> None:
        leaning = drift_block(alpha_usd=20.0, drift_usd=150.0)   # long delta, most of its Train profit the market's drift
        # The gate's own hold on a drift carrier that reaches it (GATE-READY AT TRAIN would set such a version aside
        # before validation once the holds are on: its own tests are `test_swarm_f1_gate_ready`).
        self.settings["researcher"]["carrier_screen"] = False
        sha = self.holder("a")
        self.train_run("a", "train-a", drift=leaning)
        self.validate("a")
        self.twin_with_a_passed_incubator_review(sha)
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}
        self.assertEqual(self.gate().run()["look_held"], ["a"])
        self.assertEqual((self.store.refusals(), [h["stage"] for h in self.store.look_holds("a")]), ([], [HOLD_DRIFT_STAGE]),
                         "only a hold")
        self.revoked_then_adopted(sha, "the gate's outcome for it is held (in a, which holds the same program)", adopt)
        # The twin comes to the gate: the look holds judge it again (held again), never the bar.
        self.train_run("b", "train-b", drift=leaning)
        self.validate("b")
        out = self.gate().run()
        self.assertEqual((out["look_held"], out["refused"], self.stages()), (["b"], [], []))
        # And with the holds off a third holder is read and looked at.
        self.holder("c")
        self.train_run("c", "train-c")
        self.on_gym(stronger)
        self.validate_own("c")
        self.settings["gate"]["look_holds"] = None
        reads = self.reads()
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual((out["looked"], out["refused"], self.reads() - reads, self.stages()),
                         ([{"family": "c", "passed": True}], [], 2, []))
        self.assertEqual(self.store.family("c")["band"], "candidate")

    def test_a_hold_in_a_twin_is_no_bar_after_a_league_live_only_adoption(self):
        self.held(self.new_live)

    def test_a_hold_in_a_twin_is_no_bar_after_a_new_gym(self):
        self.held(self.new_gym)

    def gym_refused(self, adopt) -> None:
        sha = self.holder("a")
        self.train_run("a", "train-a")
        self.validate("a")
        self.pool.fail.add("a")
        self.replies = [PASS, PASS]
        for _ in range(3):
            self.gate().run()
        self.assertEqual(self.stages(), [("a", "gym")], "the gate box failed three times: no one judged the program")
        self.twin_with_a_passed_incubator_review(sha)
        self.revoked_then_adopted(sha, "the gate refused it in a@1 (the gym)", adopt)
        # The gate fixed and the count reset (the operator's step): the program gets its one look in the twin.
        self.store.put(f"look_tries:{sha}", 0)
        self.train_run("b", "train-b")
        self.validate("b")
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual((out["looked"], out["refused"], self.stages()),
                         ([{"family": "b", "passed": True}], [], [("a", "gym")]))

    def test_the_gym_refusal_in_a_twin_is_no_bar_after_a_league_live_only_adoption(self):
        self.gym_refused(self.new_live)

    def test_the_gym_refusal_in_a_twin_is_no_bar_after_a_new_gym(self):
        self.gym_refused(self.new_gym)

    def test_a_verdict_in_the_twin_still_bars_behind_a_revocation(self):
        """The revocation is none, and the verdict it was made for is read where it stands: the twin's refusal row."""
        sha = self.holder("a")
        self.train_run("a", "train-a")
        self.validate("a")
        self.replies = [FAIL]
        self.assertEqual(self.gate().run()["refused"], ["a"])
        self.twin_with_a_passed_incubator_review(sha)
        self.gate().run()
        self.assertEqual(self.state("b")["incubator_reviews"][sha]["stage"], "gate")
        self.new_gym()
        self.assertEqual(self.state("b")["incubator_barred"][sha]["why"], f"the incubator's {incubator.REVOKED_WORDS}")
        self.assertEqual(incubator.look_route_bar(self.store, "b", 1, sha), "the gate refused it in a@1 (the review)")


class UnderTheLock(BarCase):
    def test_a_verdict_landing_after_the_rounds_check_stops_the_look(self):
        """Reviewed and audited (a pass), waiting for its look: a verdict against the same program lands in another
        family. `look()` reads the bar again under the store's lock and starts no look; the next round refuses it."""
        sha = self.holder("b")
        self.validate()
        self.settings["gym"]["gate_checkpoint"] = None   # reviewed and waiting for the gate image
        self.replies = [PASS, PASS]
        self.assertEqual(self.gate().run()["waiting"], ["b"])
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        self.holder("a")
        self.store.refuse("a", 1, "audit", "a verdict made in another family meanwhile")
        gate = self.gate()
        self.assertIsNone(gate.look(self.store.family("b"), self.store.version("b", 1), sha), "no look starts")
        state = self.state("b")
        self.assertEqual((self.holdout_jobs(), self.store.looks(), state.get("look_inflight"), state["gate_ready"]),
                         ([], [], None, True), "nothing read, nothing reserved; the next round records the refusal")
        reads = self.reads()
        out = self.gate().run()
        self.assertEqual((out["refused"], out["looked"], self.reads() - reads), (["b"], [], 0))
        self.assertEqual(self.stages("b"), [("b", PROGRAM_BAR_STAGE)])
        self.assertEqual(self.state("b")["review"]["verdict"], "pass", "its own passed review bought it no look")

    def test_a_verdict_landing_while_the_gate_box_runs_stops_the_band(self):
        """NO BAND ON A BARRED PROGRAM. `look()` read the bar under the lock and the job went out; while the box runs,
        a verdict against the same program lands in another family (the incubator's audit of a twin). The look is made
        and counted, and passes; no band is written: the version is refused at the bar, and the owner is told."""
        sha = self.holder("a")
        self.validate("a")
        self.holder("b")
        run = self.pool.run

        def during(job, timeout=None, late=None, late_fail=None):
            if job.window == "holdout":
                incubator.record_bar(self.store, "b", sha, "the incubator's audit failed it", version=1, clock=self.clock)
            return run(job, timeout, late, late_fail)

        self.pool.run = during
        self.replies = [PASS, PASS]
        out = self.gate().run()
        bar = "the incubator's audit failed it (in b, which holds the same program)"
        [look] = self.store.looks()
        self.assertEqual((out["looked"], look["family"], look["passed"], look["run_sha"]),
                         ([{"family": "a", "passed": True}], "a", 1, sha),
                         "the look is made and counted: its row and its p-value are kept")
        fam = self.store.family("a")
        state = fam["state"]
        self.assertEqual((fam["band"], state.get("banded_version"), bands.read(self.root)), ("gym", None, []), "no band")
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.band"], [])
        self.assertEqual((self.stages("a"), state["gated_sha"], state["gate_ready"], state["gate_outcome"]["result"]),
                         ([("a", PROGRAM_BAR_STAGE)], sha, False, "refused"))
        self.assertEqual(state["gate"], f"fail (the {PROGRAM_BAR_STAGE}: {PROGRAM_BAR_WORDS})", "never told it passed")
        [event] = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "program_bar"]
        [alert] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                   and e["payload"].get("action") == "look_passed_barred"]
        self.assertEqual((event["bar"], alert["bar"], alert["alert"], alert["version"]), (bar, bar, True, 1))
        # A pass with no verdict against it is banded as before (the same round, the bar landing nowhere).
        self.pool.run = run
        self.holder("c", CODE + "# another program\n")
        self.answer = stronger
        self.validate("c")
        self.replies = [PASS, PASS]
        self.assertEqual(self.gate().run()["looked"], [{"family": "c", "passed": True}])
        self.assertEqual(self.store.family("c")["band"], "candidate")

    def test_the_familys_own_failed_review_refuses_at_its_own_stage_with_its_reasons(self):
        """A failed review the gate holds and has not refused on yet (an operator's hold landed between its stages) is
        not swallowed by the bar: the round refuses it at the review's own stage, and the researcher reads why."""
        from league.gym.review_contract import review_contract

        sha = self.holder("a")
        self.validate()
        failed = {"sha": sha, "version": 1, "verdict": "fail", "reasons": ["counts sessions to the year"],
                  "contract_sha": review_contract()["sha256"]}
        incubator.record_bar(self.store, "a", sha, "the gate's reviewer failed it", version=1, clock=self.clock)
        self.store.set_state("a", review=failed)
        reads = self.reads()
        out = self.gate().run()
        self.assertEqual((out["refused"], self.reads() - reads, self.stages()), (["a"], 0, [("a", "review")]))
        self.assertIn("counts sessions to the year", self.state("a")["gate"])


if __name__ == "__main__":
    unittest.main()

"""EVIDENCE V3's own gate (`league/swarm/gate.py`, `Gate(sealed_looks=False)`): a validated version closed to PRACTICE
(no review, no audit, no look), and THE PRE-FILTER: one free read of a practised program's 2026 holdout for the forward
ladder, judged on THE PRE-FILTER'S LINE (its net P&L not negative AND its moving-block bootstrap p-value at or under
the constitution's `prefilter_p`), with no look row, no Holm, no look budget and no word to the researcher.

As shipped (THE FAST LANE, release F1, Oct 3, 2026) the sealed look is the route and this gate is reached only here.
ONE HOLDOUT READ A PROGRAM (`OneHoldoutRead`): the look and the pre-filter never both read a program's holdout, by the
switch and by the records, each way."""

from __future__ import annotations

import json
import random
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from league.live import ladder as L
from league.swarm import evidence as E
from league.swarm import gate as G
from league.swarm.gate import Gate, run_sha
from league.swarm.pool import PoolError
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_rounds import RoundCase, strong


PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}


class TheDefault(unittest.TestCase):
    def test_the_sealed_look_runs_by_default(self):
        """THE FAST LANE (release F1): the sealed look is the route to Probe. (Release A2 shipped it False.)"""
        self.assertIs(G.SEALED_LOOKS, True)

    def test_the_prefilter_has_one_call_site_and_it_is_under_the_switch(self):
        """By the switch: a round makes pre-filter reads only while sealed looks are off."""
        source = Path(G.__file__).read_text(encoding="utf-8")
        calls = [m.start() for m in re.finditer(r"self\.prefilter_round\(", source)]
        self.assertEqual(len(calls), 1, "one call site in the gate")
        before = source[:calls[0]].splitlines()
        self.assertEqual((before[-1].strip(), before[-2].strip()),
                         ("read =", "if not self.sealed_looks and not self.alarm():"))
        repo = Path(G.__file__).resolve().parents[2]
        others = [p for p in (repo / "league").rglob("*.py") if "tests" not in p.parts and p != Path(G.__file__)
                  and "prefilter_round(" in p.read_text(encoding="utf-8")]
        self.assertEqual(others, [], "and no other caller in the tree")


class Practice(RoundCase):
    def setUp(self):
        super().setUp()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=False)

    def validated(self, fid="a") -> str:
        self.family(fid)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])
        return run_sha(self.store.version(fid, 1))

    def test_a_validated_version_goes_to_practice_with_nothing_paid_and_nothing_opened(self):
        sha = self.validated()
        jobs = len(self.pool.jobs)
        out = self.gate.run()
        self.assertEqual(out["practice"], ["a"])
        state = self.store.family("a")["state"]
        self.assertEqual((state["gated_sha"], state["gate_ready"], state["gate_outcome"]["result"], state["gate"]),
                         (sha, False, G.PRACTICE_OUTCOME, G.PRACTICE_WORDS))
        self.assertEqual(self.pool.jobs[jobs:], [], "no sealed read")
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), 0)
        self.assertIsNone(state.get("review"))
        self.assertEqual((self.sail.bodies, self.asked), ([], []), "no review or audit paid")
        self.assertEqual(self.store.refusals("a"), [])
        self.assertNotIn(sha, state.get("incubator_barred") or {}, "practice is no verdict against the program")
        self.assertEqual(self.gate.run()["practice"], [], "the gate is done with it")

    def test_the_operator_hold_and_a_stale_validation_still_wait(self):
        self.validated()
        self.store.hold_gate("a", True, reason="test")
        self.assertEqual(self.gate.run()["held"], ["a"])
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])

    def test_the_drift_screen_still_refuses(self):
        self.validated()
        self.settings["tournament"]["drift_screen"] = True
        out = self.gate.run()
        self.assertEqual(out["practice"], [])
        self.assertTrue(out["refused"] or out["waiting"], out)

    def test_the_gate_as_shipped_sends_nothing_to_practice(self):
        self.validated()
        self.replies = []
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual(out["practice"], [])


class PrefilterCase(RoundCase):
    """`a` and `b` on a named Gym bundle, and evidence v3's own gate (`self.gate`, sealed looks off); no tests of its
    own."""

    def setUp(self):
        super().setUp()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=False)
        self.pnl = {"a": 120.0, "b": -40.0}
        self.daily: dict[str, list[float]] = {}          # a family's holdout days (default: the fakes', every day up)
        self.answer = self.holdout
        self.pool.bundle = lambda: "b1"
        for fid in ("a", "b"):
            self.family(fid)
        self.sha = {fid: run_sha(self.store.version(fid, 1)) for fid in ("a", "b")}

    def holdout(self, job):
        if job.window != "holdout":
            return strong(job)
        out = result(job.name, window="holdout", pnl=self.pnl[job.family], daily=self.daily.get(job.family))
        out["gym_bundle"], out["gym_image"] = "b1", "sbcp_gate"
        return out

    def ask(self, *fids, bundle="b1"):
        self.store.put(G.PREFILTER_REQUESTS, {self.sha[f]: {"family": f, "version": 1, "bundle": bundle,
                                                            "day": f"2026-11-0{i + 2}"} for i, f in enumerate(fids)})

    def read(self, fid):
        return self.store.get(G.PREFILTER_KEY + self.sha[fid])


class Prefilter(PrefilterCase):
    def test_one_free_read_written_for_the_ladder(self):
        self.ask("a")
        out = self.gate.prefilter_round()
        self.assertEqual(out, {"sha": self.sha["a"][:12], "status": "done", "passed": True})
        rec = self.read("a")
        self.assertEqual((rec["status"], rec["passed"], rec["pnl"], rec["bundle"], rec["ran_bundle"], rec["image"]),
                         ("done", True, 120.0, "b1", "b1", "sbcp_gate"))
        boot = E.block_bootstrap([3.0 + (i % 5) - 1.5 for i in range(250)], block=5, draws=2000,
                                 seed="prefilter:" + self.sha["a"])
        self.assertEqual((rec["p"], rec["level"]), (boot["p"], 0.02),
                         "block 5 and 2,000 draws over every day of the read, seeded by the program's run sha")
        self.assertEqual(rec["p"], 1.0 / 2001, "no resampled mean at or below zero: the floor")
        [job] = self.pool.jobs
        self.assertEqual((job.window, job.purpose, job.family), ("holdout", "prefilter", "a"))
        self.assertTrue(job.gate.startswith("pre-filter"))
        self.assertEqual(self.store.looks(), [], "no look row")
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), 0, "no look budget")
        state = self.store.family("a")["state"]
        self.assertIsNone(state.get("gated_sha"))
        self.assertIsNone(state.get("gate"), "no word to the researcher")
        [event] = [e for e in self.store.events_after(0) if e["payload"].get("action") == "prefilter"]
        self.assertEqual(event["payload"]["_figures"], {"pnl": 120.0, "p": rec["p"]}, "the figures are kept private")
        self.assertEqual({k for k in event["payload"] if not k.startswith("_")},
                         {"action", "version", "sha", "status", "passed"})
        self.assertEqual([r["purpose"] for r in self.store.runs("a", window="holdout")], ["prefilter"])
        self.assertIsNone(self.gate.prefilter_round(), "answered: not read again")
        self.assertEqual(len(self.pool.jobs), 1)

    def test_a_negative_read_does_not_pass_and_one_read_a_round(self):
        self.ask("a", "b")
        self.gate.prefilter_round()
        self.assertEqual(len(self.pool.jobs), 1)
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["passed"], self.read("b")["passed"]), (True, False))
        self.assertEqual(len(self.pool.jobs), 2)
        b = self.read("b")
        self.assertEqual((b["pnl"], b["p"], b["level"]), (-40.0, 1.0 / 2001, 0.02),
                         "its days resample above zero, and its net P&L after fees is negative: it does not pass")

    def test_a_read_that_made_money_by_a_margin_its_noise_explains_does_not_pass(self):
        rng = random.Random(5)
        self.daily["a"] = [rng.gauss(0.4, 10.0) for _ in range(180)]
        self.pnl["a"] = sum(self.daily["a"])
        self.ask("a")
        self.assertEqual(self.gate.prefilter_round(), {"sha": self.sha["a"][:12], "status": "done", "passed": False})
        rec = self.read("a")
        self.assertGreater(rec["pnl"], 0)
        self.assertGreater(rec["p"], 0.02)
        self.assertEqual(rec["p"], E.block_bootstrap(self.daily["a"], seed="prefilter:" + self.sha["a"])["p"])
        self.assertIsNone(self.gate.prefilter_round(), "answered on the line: not read again")

    def test_the_line_is_the_constitutions_and_a_tighter_one_is_the_one_judged_at(self):
        self.assertEqual(G.prefilter_level(), L.Rules.from_constitution().prefilter_p)
        self.assertEqual(G.prefilter_level(), 0.02)
        rng = random.Random(4)
        self.daily["a"] = [rng.gauss(0.6, 10.0) for _ in range(180)]     # a p-value between 0.005 and 0.02
        self.pnl["a"] = sum(self.daily["a"])
        self.ask("a")
        with patch.object(G, "prefilter_level", return_value=0.005):
            self.gate.prefilter_round()
        rec = self.read("a")
        self.assertTrue(0.005 < rec["p"] <= 0.02, rec["p"])
        self.assertEqual((rec["passed"], rec["level"]), (False, 0.005))
        self.assertEqual(E.prefilter_line({"summary": {"pnl": rec["pnl"]}, "daily": [["d", x] for x in self.daily["a"]]},
                                          level=0.02, seed="prefilter:" + self.sha["a"])["passed"], True)

    def test_a_refused_money_table_reads_nothing(self):
        self.ask("a")
        with patch.object(L.Rules, "from_constitution", side_effect=ValueError("the forward ladder's table is refused")):
            self.assertIsNone(G.prefilter_level())
            self.assertIsNone(self.gate.prefilter_round())
        self.assertEqual((self.pool.jobs, self.read("a")), ([], None))

    def test_a_record_from_before_the_line_is_no_answer_and_is_read_again(self):
        self.ask("a")
        old = {"status": "done", "passed": True, "pnl": 120.0, "bundle": "b1", "ran_bundle": "b1", "image": "sbcp_gate",
               "family": "a", "version": 1, "tries": 0, "why": None, "at": 1.0}       # only its P&L's sign was read
        self.store.put(G.PREFILTER_KEY + self.sha["a"], old)
        self.assertFalse(G.prefilter_judged(old))
        self.assertEqual(self.gate.prefilter_round()["status"], "done")
        self.assertEqual(len(self.pool.jobs), 1, "read again")
        rec = self.read("a")
        self.assertEqual((rec["level"], rec["passed"], G.prefilter_judged(rec)), (0.02, True, True))
        self.assertIsNone(self.gate.prefilter_round())
        self.assertEqual(len(self.pool.jobs), 1)

    def test_the_ladder_reads_the_gates_record_as_both_conditions(self):
        rng = random.Random(5)
        self.daily["b"] = [rng.gauss(0.4, 10.0) for _ in range(180)]
        self.pnl["b"] = sum(self.daily["b"])                 # b made money, over the line on its p-value
        self.ask("a", "b")
        self.gate.prefilter_round()
        self.gate.prefilter_round()
        a, b = self.read("a"), self.read("b")
        self.assertEqual(L.prefilter_answer(a, bundle="b1", level=0.02),
                         {"passed": True, "pnl": 120.0, "p": a["p"], "level": 0.02})
        self.assertEqual(L.prefilter_answer(b, bundle="b1", level=0.02),
                         {"passed": False, "pnl": b["pnl"], "p": b["p"], "level": 0.02})
        self.assertIsNone(L.prefilter_answer(a, bundle="b2", level=0.02), "the House runs another bundle")
        self.assertIsNone(L.prefilter_answer({k: v for k, v in a.items() if k not in ("p", "level")}, bundle="b1",
                                             level=0.02), "a record without the line is not a pass: asked again")

    def test_a_read_that_cannot_be_made_now_waits_without_a_try_and_does_not_block_the_next(self):
        self.ask("a", "b")
        self.store.put(G.PREFILTER_REQUESTS, {**self.store.get(G.PREFILTER_REQUESTS),
                                              self.sha["a"]: {"family": "a", "version": 1, "bundle": "b0", "day": "2026-11-01"}})
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["status"], self.read("a")["tries"]), ("waiting", 0))
        self.assertIn("another Gym bundle", self.read("a")["why"])
        self.assertEqual(self.read("b")["status"], "done", "the next request is read")
        events = len(self.store.events_after(0))
        self.gate.prefilter_round()
        self.assertEqual(len(self.store.events_after(0)), events, "the same waiting record is not written again")

    def test_no_gate_image_waits(self):
        self.settings["gym"]["gate_checkpoint"] = None
        self.ask("a")
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["status"], self.pool.jobs), ("waiting", []))

    def test_three_failed_reads_leave_it_failed(self):
        self.ask("a")
        self.pool.fail.add("a")
        for tries in (1, 2):
            self.gate.prefilter_round()
            self.assertEqual((self.read("a")["status"], self.read("a")["tries"]), ("waiting", tries))
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["status"], self.read("a")["tries"]), ("failed", 3))
        self.gate.prefilter_round()
        self.assertEqual(len(self.pool.jobs), 3, "out of tries: never read again on that bundle")

    def test_a_read_the_guards_brake_kept_from_a_gate_box_is_no_try(self):
        """A BRAKED ROUND IS NOT A TRY (B11): a read that never reached a box while the guard allows no gate box waits
        with its tries as they were; three of them never leave it failed. One the Gym failed while the guard allowed a
        box counts, as before."""
        self.ask("a")
        self.pool.fail.add("a")
        allowed = {"gate": False}
        self.pool.allowed = lambda kind: allowed[kind]
        for _ in range(4):
            self.gate.prefilter_round()
            self.assertEqual((self.read("a")["status"], self.read("a")["tries"], self.read("a")["why"]),
                             ("waiting", 0, "the budget guard allowed no gate box"))
        self.assertEqual(len(self.pool.jobs), 4, "asked again every round")
        allowed["gate"] = True  # the guard allows a box again, and the Gym still fails: that is a try
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["status"], self.read("a")["tries"]), ("waiting", 1))
        self.pool.fail.clear()
        self.gate.prefilter_round()
        self.assertEqual((self.read("a")["status"], self.read("a")["passed"]), ("done", True))

    def test_a_program_not_in_the_store_fails_and_the_alarm_stops_every_read(self):
        self.store.put(G.PREFILTER_REQUESTS, {"nope": {"family": "a", "version": 1, "bundle": "b1", "day": "x"}})
        self.gate.prefilter_round()
        self.assertEqual(self.store.get(G.PREFILTER_KEY + "nope")["status"], "failed")
        self.ask("a")
        for i in range(10):
            self.store.add_look("b", 1, f"sha{i}", passed=i < 4, p_value=0.5, detail={})
        out = self.gate.run()
        self.assertTrue(out.get("alarm"))
        self.assertEqual(self.pool.jobs, [])

    def test_a_round_reads_one(self):
        self.ask("a")
        self.assertEqual(self.gate.run()["prefilter"]["status"], "done")


class OneHoldoutRead(PrefilterCase):
    """ONE HOLDOUT READ A PROGRAM (release F1; the gate's module docstring), by the switch and by the records, each way.
    `self.shipped` is the gate as the tree ships it (the sealed look runs); `self.gate` is evidence v3's own."""

    def setUp(self):
        super().setUp()
        self.shipped = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.pool.image = lambda kind="gym": "sbcp_gate"
        self.answer = lambda job: {**self.holdout(job), "gym_bundle": "b1", "gym_image": "sbcp_gate"}

    def at_the_gate(self, fid="a"):
        Tournament(self.store, self.pool, self.settings).validate([self.store.family(fid)])
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])

    def holdout_jobs(self):
        return [(j.family, j.purpose) for j in self.pool.jobs if j.window == "holdout"]

    # ---- by the switch
    def test_as_shipped_the_prefilter_never_reads_beside_the_look(self):
        self.at_the_gate()
        self.ask("a")
        ask = self.store.get(G.PREFILTER_REQUESTS)
        self.replies = [PASS, PASS]
        out = self.shipped.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])
        self.assertEqual(self.holdout_jobs(), [("a", "holdout")], "one read of the holdout: the counted look's")
        self.assertNotIn("prefilter", out)
        self.assertEqual((self.read("a"), self.store.get(G.PREFILTER_REQUESTS)), (None, ask),
                         "no pre-filter record is written, and the request is the House's: left as it is")
        for _ in range(3):
            self.clock.advance(600)
            self.shipped.run()
        self.assertEqual((self.holdout_jobs(), len(self.store.looks())), ([("a", "holdout")], 1), "round after round: one")

    # ---- by the records, one way: a program the gate looked at is never read by the pre-filter
    def test_the_prefilter_never_reads_a_program_that_has_a_look_row(self):
        self.at_the_gate()
        self.replies = [PASS, PASS]
        self.assertEqual(self.shipped.run()["looked"], [{"family": "a", "passed": True}])
        self.ask("a", "b")
        # Someone switches sealed looks off again (or a tool runs evidence v3's own gate): the record says why.
        out = self.gate.prefilter_round()
        self.assertEqual(self.read("a")["status"], "failed")
        self.assertEqual((self.read("a")["why"], self.read("a")["tries"]), (G.PREFILTER_LOOKED, 0))
        self.assertEqual(out, {"sha": self.sha["b"][:12], "status": "done", "passed": False}, "the next request is read")
        self.assertEqual(self.holdout_jobs(), [("a", "holdout"), ("b", "prefilter")], "a's holdout: read once, by its look")
        self.assertIsNone(L.prefilter_answer(self.read("a"), bundle="b1", level=0.02), "no answer for the ladder: unanswered")
        self.assertIsNone(self.gate.prefilter_round(), "and never asked again")
        self.assertEqual(len(self.pool.jobs), 3)
        # A failed look is a look too, and the same program in another family is the same program.
        self.store.add_look("b", 1, "f" * 64, passed=False, p_value=0.9, detail={})
        self.store.put(G.PREFILTER_REQUESTS, {"f" * 64: {"family": "b", "version": 1, "bundle": "b1", "day": "2026-11-09"}})
        self.gate.prefilter_round()
        self.assertEqual(self.store.get(G.PREFILTER_KEY + "f" * 64)["why"], G.PREFILTER_LOOKED)

    def test_the_prefilter_waits_while_a_look_at_the_program_is_in_flight(self):
        self.store.set_state("b", look_inflight={"sha": self.sha["a"], "n": 1, "at": self.clock(), "token": "t"})
        self.ask("a")
        self.assertEqual(self.gate.prefilter_round()["status"], "waiting")
        self.assertEqual((self.read("a")["why"], self.read("a")["tries"], self.pool.jobs), (G.PREFILTER_LOOKING, 0, []))
        self.store.set_state("b", look_inflight=None)
        self.assertEqual(self.gate.prefilter_round()["status"], "done", "the look never landed: the read is made")

    # ---- by the records, the other way: a program the pre-filter read is never looked at
    def test_the_look_holds_a_program_whose_prefilter_record_is_done_with_one_alert(self):
        self.ask("a")
        self.assertEqual(self.gate.prefilter_round()["status"], "done")     # evidence v3's own gate read its holdout
        self.at_the_gate()
        paid = len(self.sail.bodies) + len(self.asked)
        self.replies = [PASS, PASS]
        out = self.shipped.run()
        self.assertEqual((out["look_held"], out["looked"], out["refused"]), (["a"], [], []))
        self.assertEqual(self.holdout_jobs(), [("a", "prefilter")], "its holdout: read once, by the pre-filter")
        self.assertEqual((self.store.looks(), len(self.sail.bodies) + len(self.asked) - paid), ([], 0),
                         "no look row, and no review or audit paid for a look that cannot be made")
        [row] = self.store.look_holds("a")
        self.assertEqual((row["stage"], row["reason"]), (G.HOLD_READ_STAGE, G.HOLD_WORDS[G.HOLD_READ_STAGE]))
        state = self.store.family("a")["state"]
        self.assertEqual((state["gated_sha"], state["gate_ready"], state["gate_outcome"]["result"], state["gate"]),
                         (self.sha["a"], False, G.HOLD_OUTCOME, G.HOLD_WORDS[G.HOLD_READ_STAGE]))
        self.assertEqual(self.store.refusals("a"), [], "a hold, never a refusal")
        alerts = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "holdout_read_before_look"]
        self.assertEqual([(a["alert"], a["version"]) for a in alerts], [(True, 1)])
        self.assertIn("one read of the holdout", alerts[0]["text"])
        for _ in range(3):
            self.clock.advance(600)
            self.shipped.run()
        self.assertEqual(len([e for e in self.store.events_after(0)
                              if e["payload"].get("action") == "holdout_read_before_look"]), 1, "one alert")
        self.assertEqual((self.holdout_jobs(), self.store.looks()), ([("a", "prefilter")], []))

    def test_the_look_reads_the_record_again_under_the_lock(self):
        """The pre-filter's record lands between the round's checks and the look: `look()` starts none."""
        self.at_the_gate()
        fam = self.store.family("a")
        self.store.put(G.PREFILTER_KEY + self.sha["a"], {"status": "done", "passed": True, "bundle": "b1", "level": 0.02})
        self.assertIsNone(self.shipped.look(fam, self.store.version("a", 1), self.sha["a"]))
        state = self.store.family("a")["state"]
        self.assertEqual((self.holdout_jobs(), state.get("look_inflight"), state["gate_ready"]), ([], None, True),
                         "no read, no marker; the next round records the hold")
        self.assertEqual(self.shipped.run()["look_held"], ["a"])

    def test_a_record_with_no_read_made_holds_nothing(self):
        """Waiting and failed records are no read of the holdout: the look goes ahead."""
        self.at_the_gate()
        for record in ({"status": "waiting", "bundle": "b1", "tries": 1}, {"status": "failed", "bundle": "b1", "tries": 3}):
            self.store.put(G.PREFILTER_KEY + self.sha["a"], record)
            self.assertIsNone(self.shipped.read_hold(self.sha["a"]), record)
        self.replies = [PASS, PASS]
        self.assertEqual(self.shipped.run()["looked"], [{"family": "a", "passed": True}])


if __name__ == "__main__":
    unittest.main()

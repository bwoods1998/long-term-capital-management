"""EVIDENCE V3 at the gate (`league/swarm/gate.py`): the sealed look retired, a validated version closed to PRACTICE (no
review, no audit, no look), and THE PRE-FILTER: one free read of a practised program's 2026 holdout for the forward
ladder, with no look row, no Holm, no look budget and no word to the researcher."""

from __future__ import annotations

import unittest

from league.swarm import gate as G
from league.swarm.gate import Gate, run_sha
from league.swarm.pool import PoolError
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_rounds import RoundCase, strong


class TheDefault(unittest.TestCase):
    def test_the_sealed_look_is_retired_by_default(self):
        self.assertIs(G.SEALED_LOOKS, False)


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

    def test_the_retired_route_is_still_reached_explicitly(self):
        self.validated()
        self.replies = []
        out = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=True).run()
        self.assertEqual(out["practice"], [])


class Prefilter(RoundCase):
    def setUp(self):
        super().setUp()
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock, sealed_looks=False)
        self.pnl = {"a": 120.0, "b": -40.0}
        self.answer = self.holdout
        self.pool.bundle = lambda: "b1"
        for fid in ("a", "b"):
            self.family(fid)
        self.sha = {fid: run_sha(self.store.version(fid, 1)) for fid in ("a", "b")}

    def holdout(self, job):
        if job.window != "holdout":
            return strong(job)
        out = result(job.name, window="holdout", pnl=self.pnl[job.family])
        out["gym_bundle"], out["gym_image"] = "b1", "sbcp_gate"
        return out

    def ask(self, *fids, bundle="b1"):
        self.store.put(G.PREFILTER_REQUESTS, {self.sha[f]: {"family": f, "version": 1, "bundle": bundle,
                                                            "day": f"2026-11-0{i + 2}"} for i, f in enumerate(fids)})

    def read(self, fid):
        return self.store.get(G.PREFILTER_KEY + self.sha[fid])

    def test_one_free_read_written_for_the_ladder(self):
        self.ask("a")
        out = self.gate.prefilter_round()
        self.assertEqual(out, {"sha": self.sha["a"][:12], "status": "done", "passed": True})
        rec = self.read("a")
        self.assertEqual((rec["status"], rec["passed"], rec["pnl"], rec["bundle"], rec["ran_bundle"], rec["image"]),
                         ("done", True, 120.0, "b1", "b1", "sbcp_gate"))
        [job] = self.pool.jobs
        self.assertEqual((job.window, job.purpose, job.family), ("holdout", "prefilter", "a"))
        self.assertTrue(job.gate.startswith("pre-filter"))
        self.assertEqual(self.store.looks(), [], "no look row")
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), 0, "no look budget")
        state = self.store.family("a")["state"]
        self.assertIsNone(state.get("gated_sha"))
        self.assertIsNone(state.get("gate"), "no word to the researcher")
        [event] = [e for e in self.store.events_after(0) if e["payload"].get("action") == "prefilter"]
        self.assertEqual(event["payload"]["_figures"], {"pnl": 120.0}, "the figure is kept private")
        self.assertNotIn("pnl", {k for k in event["payload"] if not k.startswith("_")})
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


if __name__ == "__main__":
    unittest.main()

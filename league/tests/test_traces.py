"""Research traces: private bodies, a ledger pointer, outcomes joined append-only."""
from decimal import Decimal
import json
import os
from pathlib import Path
import stat
import tempfile

from league.traces import TraceStore, research_outcome
from league.tests.test_researcher import CODE, ResearchCase


class Traces(ResearchCase):
    def test_a_finished_pass_leaves_a_private_body_and_a_pointer(self):
        researcher = self.researcher([
            [("replay", {"code": CODE, "purpose": "test a cheaper rule"})],
            [("finish", {"summary": "The candidate failed replay; recorded."})],
        ])
        store = TraceStore(self.dir.name, self.ledger, clock=self.clock)
        researcher.traces = store
        researcher.research(self.parent, {"cash": 3}, session="s-trace")
        pointers = [e.payload for e in self.ledger.iter(kinds="trace.record")]
        self.assertEqual(len(pointers), 1)
        pointer = pointers[0]
        self.assertEqual((pointer["task"], pointer["version"], pointer["outcome"], pointer["useful"]),
                         ("research", 1, "candidate_failed", False))
        self.assertEqual(len(pointer["inputs_sha256"]), 64)
        self.assertNotIn("inputs", pointer)  # bodies never reach the ledger
        body = store.read(pointer["id"])
        self.assertEqual(body["inputs_sha256"], pointer["inputs_sha256"])
        self.assertEqual(body["candidate"]["code"], CODE)
        self.assertTrue(body["outputs"])
        self.assertEqual(stat.S_IMODE(os.stat(store.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(store.path(pointer["id"])).st_mode), 0o600)

    def test_later_outcomes_are_new_versions_and_repeats_add_nothing(self):
        store = TraceStore(self.dir.name, self.ledger, clock=self.clock)
        first = store.capture("repair", key="missing_data:funding", model="gpt-6-astra", inputs={"issue": 1},
                              outputs={"patch": "diff"}, cost_usd=Decimal("0.5"), outcome="proposed", useful=None)
        again = store.capture("repair", key="missing_data:funding", model="gpt-6-astra", inputs={"issue": 1},
                              outputs={"patch": "diff"}, cost_usd=Decimal("0.5"), outcome="proposed", useful=None)
        self.assertEqual(first, again)
        self.assertEqual(store.outcome(first["id"], outcome="verified", useful=True)["version"], 2)
        self.assertEqual(store.outcome(first["id"], outcome="verified", useful=True)["version"], 2)
        rows = [e.payload for e in self.ledger.iter(kinds="trace.record")]
        self.assertEqual([(r["version"], r["outcome"]) for r in rows], [(1, "proposed"), (2, "verified")])
        self.assertIsNone(store.outcome("no-such-trace", outcome="x", useful=None))

    def test_outcomes_follow_the_pass(self):
        from league.researcher import Pass
        self.assertEqual(research_outcome(Pass("a", candidate={"passed": True})), ("candidate_passed", True))
        self.assertEqual(research_outcome(Pass("a", reason="finished")), ("abstained", None))
        self.assertEqual(research_outcome(Pass("a", reason="provider: http_503"))[1], False)

    def test_a_broken_store_never_costs_the_pass(self):
        researcher = self.researcher([[("finish", {"summary": "nothing to do this pass at all"})]])
        researcher.traces = type("Broken", (), {"capture": lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))})()
        result = researcher.research(self.parent, {}, session="s-broken")
        self.assertEqual(result.reason, "finished")
        self.assertTrue(any("trace capture failed" in e.payload["text"] for e in self.ledger.iter(kinds="ops.alert")))


class AdoptionJoin(ResearchCase):
    def test_what_the_house_did_with_a_candidate_becomes_the_next_version(self):
        from types import SimpleNamespace
        from league.traces import adoption_outcome, trace_id
        store = TraceStore(self.dir.name, self.ledger, clock=self.clock)
        store.capture("research", key="s1", model="openai_luna", inputs={}, outputs=[], cost_usd="0.01",
                      outcome="candidate_passed", useful=True, agent=self.parent.id)
        candidate = {"code": "NEW", "passed": True}
        in_place = SimpleNamespace(get=lambda _id: SimpleNamespace(code="NEW"))
        self.assertEqual(adoption_outcome(self.ledger, in_place, self.parent.id, "s1", candidate), ("adopted", True))
        elsewhere = SimpleNamespace(get=lambda _id: SimpleNamespace(code="OLD"))
        self.assertEqual(adoption_outcome(self.ledger, elsewhere, self.parent.id, "s1", candidate), ("not_adopted", False))
        self.ledger.append("agent.research", {"tool": "candidate_admission", "session": "s1", "status": "deferred"}, agent=self.parent.id)
        self.assertEqual(adoption_outcome(self.ledger, elsewhere, self.parent.id, "s1", candidate), ("fork_deferred", False))
        self.ledger.append("agent.research", {"tool": "candidate_admission", "session": "s1", "status": "admitted", "child": "c"}, agent=self.parent.id)
        outcome, useful = adoption_outcome(self.ledger, elsewhere, self.parent.id, "s1", candidate)
        self.assertEqual((outcome, useful), ("forked", True))
        self.assertEqual(store.outcome(trace_id("research", "s1"), outcome=outcome, useful=useful, agent=self.parent.id)["version"], 2)
        # A failed-but-trading rewrite is adopted on purpose, but it is not a validated artifact.
        self.assertEqual(adoption_outcome(self.ledger, in_place, self.parent.id, "s2", {"code": "NEW", "passed": False}), ("adopted", False))

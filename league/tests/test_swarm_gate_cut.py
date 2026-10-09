"""AN ANSWER CUT SHORT IS NO ANSWER (Oct 10, 2026; the readiness audit's M2; league/swarm/gate.py `AnswerCut`,
`Gate._cut_check`). On Oct 9 the Sail stand-in reviewer came back `incomplete` at max_output_tokens four times in six,
and three cut answers in a row refused dir-qqq-ivlow-3d-call v38: a direction lineage's one try lost to a token cap.
A cut review or audit (the gate's and the incubator's) is now an error: no attempt counted, nothing barred, asked again
next round under a new model-call key, at most `gate.cut_tries_day` times a UTC day, the last of them alerting the owner.
A fake Gym pool, a scripted Sail (the real Provider), a fake gateway."""

from __future__ import annotations

import json
from unittest import mock

from league.swarm.gate import CUT_TRIES_DAY, AnswerCut, Gate, gate_contract, run_sha
from league.swarm.tournament import Tournament
from league.tests.test_swarm_rounds import RoundCase

PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
#: Sail's answer cut at the output cap: every token reasoning, no text (the House's three of 20:13-20:23Z Oct 9).
CUT = {"status": "incomplete", "incomplete_reason": "max_output_tokens", "output_tokens": 6000, "reasoning_tokens": 6000}
DAY = 86400.0


class CutAnswers(RoundCase):
    def ready(self, fid="a"):
        self.family(fid)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])

    def round(self):
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()

    def gate_events(self, action):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate"
                and e["payload"].get("action") == action]

    def request_keys(self):
        return [r[0] for r in self.provider._db.execute("SELECT request_key FROM requests ORDER BY rowid").fetchall()]

    def contract(self):
        return gate_contract()["sha256"][:12]

    def test_three_cut_reviews_are_no_verdict_and_the_fourth_answer_is_judged(self):
        self.ready()
        self.replies = [CUT, CUT, CUT, PASS, PASS]
        for _ in range(3):
            out = self.round()
            self.assertEqual((out["refused"], out["looked"]), ([], []))
            self.clock.advance(300)
        self.assertEqual(self.store.refusals("a"), [], "before the fix the third cut answer was a refusal")
        self.assertIsNone(self.store.get(f"review_attempt:{self.contract()}:a:1"), "no attempt counted")
        self.assertEqual(self.gate_events("review"), [], "a cut answer is never judged (never 'unclear')")
        errors = self.gate_events("review_error")
        self.assertEqual([(e["cut"], e["incomplete_reason"], e["cut_today"]) for e in errors],
                         [(True, "max_output_tokens", 1), (True, "max_output_tokens", 2), (True, "max_output_tokens", 3)])
        self.assertNotIn("incubator_barred", self.store.family("a")["state"], "no verdict, no bar")
        self.assertEqual(self.round()["looked"], [{"family": "a", "passed": True}], "a complete answer is judged as before")
        keys = self.request_keys()
        base = f"swarm:{self.contract()}:a:review:1:0"
        self.assertEqual(keys[:4], [base, base + ":cut1", base + ":cut2", base + ":cut3"],
                         "a new key after each cut (the Provider dedupes on it); the first ask's key as before")
        self.assertEqual(keys[4], f"swarm:{self.contract()}:a:audit:1:0", "the audit's first key as before")

    def test_a_cut_audit_counts_no_attempt_and_is_asked_again(self):
        self.ready()
        self.replies = [PASS, CUT, CUT, CUT, PASS]
        for _ in range(3):
            self.assertEqual(self.round()["looked"], [])
            self.clock.advance(300)
        self.assertEqual(self.store.refusals("a"), [])
        sha = run_sha(self.store.version("a", 1))
        self.assertIsNone(self.store.get(f"audit_attempt:{self.contract()}:{sha}"), "no attempt counted")
        self.assertEqual(len(self.gate_events("review")), 1, "the review is kept: an audit asked again does not redo it")
        self.assertEqual([e["cut"] for e in self.gate_events("audit_error")], [True, True, True])
        self.assertEqual(self.round()["looked"], [{"family": "a", "passed": True}])
        self.assertEqual(self.request_keys()[-1], f"swarm:{self.contract()}:a:audit:1:0:cut3")

    def test_the_days_last_cut_alerts_once_then_the_stage_waits_for_the_next_utc_day(self):
        self.ready()
        self.replies = [CUT] * CUT_TRIES_DAY
        for _ in range(CUT_TRIES_DAY):
            self.round()
            self.clock.advance(300)
        alerts = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                  and e["payload"].get("action") == "reader_cut"]
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["alert"])
        self.assertIn("gate.review_max_output_tokens", alerts[0]["text"])
        asked, events = len(self.sail.bodies), len(self.store.events_after(0))
        self.round()
        self.assertEqual((len(self.sail.bodies), len(self.store.events_after(0))), (asked, events),
                         "today's cut answers are used: not asked, no event, no spend")
        self.assertEqual(self.store.refusals("a"), [])
        self.clock.advance(DAY)
        self.replies = [PASS, PASS]
        self.assertEqual(self.round()["looked"], [{"family": "a", "passed": True}], "asked again the next UTC day")
        self.assertTrue(self.request_keys()[-2].endswith(f":review:1:0:cut{CUT_TRIES_DAY}"))

    def test_the_setting_sets_the_days_cap_and_a_bad_value_reads_as_the_default(self):
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        for value, cap in ((2, 2), (0, CUT_TRIES_DAY), (None, CUT_TRIES_DAY), (True, CUT_TRIES_DAY), ("3", CUT_TRIES_DAY),
                           (float("nan"), CUT_TRIES_DAY), (float("inf"), CUT_TRIES_DAY)):
            self.settings["gate"]["cut_tries_day"] = value
            self.assertEqual(gate.cut_tries_day(), cap, value)

    def test_an_unclear_complete_answer_still_counts_as_before(self):
        self.ready()
        self.replies = [CUT, {"text": "hmm"}, {"text": "hmm"}, {"text": "hmm"}]
        for _ in range(4):
            self.round()
            self.clock.advance(300)
        [refusal] = self.store.refusals("a")
        self.assertEqual(refusal["stage"], "review", "three complete unclear answers: refused, as before")

    def test_the_incubators_cut_review_is_asked_again_on_its_own_count(self):
        from league.swarm import incubator

        self.family("a")
        sha = run_sha(self.store.version("a", 1))
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.replies = [CUT, PASS, PASS]
        with mock.patch.object(incubator, "reviewable", return_value=True):
            self.assertIsNone(gate._incubator_review("a", 1, sha), "no verdict: asked again next round")
            self.assertIsNone(self.store.get(f"incubator_review_attempt:{self.contract()}:a:1"))
            self.assertIsNone(self.store.get(f"review_cut:{self.contract()}:a:1"), "the gate's own count is untouched")
            self.assertEqual(self.store.get(f"incubator_review_cut:{self.contract()}:a:1")["today"], 1)
            self.assertEqual(gate._incubator_review("a", 1, sha), "pass")
        [error] = self.gate_events("incubator_review_error")
        self.assertTrue(error["cut"])
        self.assertTrue(self.request_keys()[1].endswith(":incubator_review:1:0:cut1"))

    def test_a_truncated_flag_alone_is_a_cut(self):
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        with self.assertRaises(AnswerCut) as caught:
            gate._cut_check({"truncated": True, "incomplete_reason": None, "route": "sail", "model": "pro_balanced"},
                            "review", self.contract(), "a", 1, 6000)
        self.assertFalse(caught.exception.quiet)
        self.assertIsNone(gate._cut_check({"truncated": False, "incomplete_reason": None}, "review", self.contract(), "a", 2,
                                          6000), "a complete answer passes")

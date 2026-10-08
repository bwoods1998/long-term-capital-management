"""Grounded gate judgments: known runtime facts, reproducible claims, no inferred passes."""

import hashlib
import json
import unittest
from pathlib import Path

from league.gym.review_contract import grounded_answer, review_contract
from league.swarm.gate import Gate, REVIEW
from league.swarm.tournament import Tournament
from league.tests.test_swarm_rounds import RoundCase

CODE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    if ctx.under.price > 550:\n        return [{'cancel': 'level'}]\n    return []\n"


class ReviewEvidence(unittest.TestCase):
    def answer(self, **changes):
        raw = {"verdict": "fail", "reasons": ["a hard-coded underlying price identifies a regime"], "findings": [{
            "code_excerpt": "ctx.under.price > 550", "contract_reference": "calendar",
            "counterexample": "An otherwise identical relative market below 550 is disabled; the absolute historical level selects a known period."}]}
        raw.update(changes)
        return {"json": raw, "model": "test-model", "route": "test", "cost_usd": 0.1}

    def test_receipt_carries_actual_runtime_source_and_available_fields(self):
        packet = review_contract()
        root = Path(__file__).resolve().parents[1] / "gym"
        self.assertEqual(packet["source_sha256"]["runtime.py"], hashlib.sha256((root / "runtime.py").read_bytes()).hexdigest())
        self.assertIn("_fresh_namespace(program.params)", packet["source_excerpts"]["runtime.py:Runner.__init__"])
        self.assertIn("exec(program._compiled", packet["source_excerpts"]["runtime.py:Runner.__init__"])
        self.assertIn("PARAMS", packet["facts"]["parameters"])
        self.assertIn("prior_close", packet["context_fields"]["UnderlyingView"])
        for invented in ("date", "year", "session_id", "bar_id"):
            self.assertNotIn(invented, packet["context_fields"]["Ctx"])
        self.assertIn("fresh module state", REVIEW)
        self.assertIn("Do not claim you executed", REVIEW)

    def test_a_located_causal_counterexample_is_a_recorded_failure(self):
        out = grounded_answer(self.answer(), CODE)
        self.assertEqual(out["verdict"], "fail")
        self.assertEqual(out["findings"][0]["contract_reference"], "calendar")
        self.assertEqual(out["contract_sha"], review_contract()["sha256"])
        self.assertEqual((out["route"], out["cost_usd"]), ("test", 0.1))

    def test_unsupported_claims_never_become_passes_or_established_facts(self):
        valid = self.answer()["json"]["findings"][0]
        for findings in ([], [{**valid, "code_excerpt": "STATE['future']"}], [{**valid, "contract_reference": "imagined_api"}],
                         [{**valid, "counterexample": "maybe"}], [valid, {"bad": "receipt"}]):
            with self.subTest(findings=findings):
                out = grounded_answer(self.answer(findings=findings), CODE)
                self.assertEqual((out["verdict"], out["claimed_verdict"]), ("unclear", "fail"))
                self.assertIn("another review", out["grounding"])

    def test_no_new_requirement_for_a_pass_or_an_explicit_unclear_answer(self):
        self.assertEqual(grounded_answer({"json": {"verdict": "pass"}}, CODE)["verdict"], "pass")
        self.assertEqual(grounded_answer({"json": {"verdict": "unclear"}}, CODE)["verdict"], "unclear")
        self.assertEqual(grounded_answer({"json": ["malformed"]}, CODE)["verdict"], "unclear")


class GateContract(RoundCase):
    def ready(self):
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))

    def test_both_readers_receive_the_real_contract_and_receipts_are_durable(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.sail.bodies), 2)
        for body in self.sail.bodies:
            packet = json.dumps(body)
            self.assertIn("runtime.py:Runner.__init__", packet)
            self.assertIn("session_id", packet)  # explicitly documented as unavailable
            from league.swarm.gate import gate_contract

            self.assertIn(gate_contract()["sha256"], packet)  # the gate's contract: the Gym's plus the computed fields
            self.assertIn('\\"delta\\"', packet)  # the contract travels JSON-escaped inside the request body
        review = self.store.family("a")["state"]["review"]
        self.assertEqual(review["contract_sha"], review["audit"]["contract_sha"])

    def test_ungrounded_rejection_retries_then_refuses_without_spending_a_look(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "fail", "reasons": ["STATE could leak"]})}] * 3
        gate = Gate(self.store, self.pool, self.router, self.settings)
        gate.run()
        self.assertEqual((self.store.looks(), self.store.refusals("a")), ([], []))
        gate.run()
        gate.run()
        self.assertEqual(self.store.looks(), [])
        [refusal] = self.store.refusals("a")
        self.assertIn("could not reach a verdict", refusal["reason"])
        event = next(e for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == "review")
        self.assertEqual(event["payload"]["claimed_verdict"], "fail")
        self.assertEqual(event["payload"]["findings"], [])

    def test_invalid_parameter_variant_never_pays_a_reader_or_opens_a_holdout(self):
        self.family("a")
        version = self.store.add_version("a", "NEEDS = {'roots': ['SPY']}\nPARAMS = {'unused': 1}\ndef decide(ctx):\n    return []\n",
                                         {"unused": 2}, author="test")
        self.store.update_family("a", best_version=version["n"])
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["refused"], ["a"])
        self.assertEqual((self.sail.bodies, self.asked, self.store.looks()), ([], [], []))
        [refusal] = self.store.refusals("a")
        self.assertEqual(refusal["stage"], "experiment contract")
        self.assertIn("never read", refusal["reason"])

    def test_old_cached_review_cannot_cross_a_runtime_contract_change(self):
        self.ready()
        from league.swarm.gate import run_sha

        version = self.store.version("a", 1)
        self.store.set_state("a", review={"sha": run_sha(version), "contract_sha": "old-runtime", "verdict": "pass",
                                          "audit": {"verdict": "pass"}})
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.sail.bodies), 2)
        from league.swarm.gate import gate_contract

        self.assertEqual(self.store.family("a")["state"]["review"]["contract_sha"], gate_contract()["sha256"])


if __name__ == "__main__":
    unittest.main()

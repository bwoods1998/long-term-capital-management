"""The adversarial review of R2 and R3 (#276, the close-the-gaps run, Sept 24, 2026): what the seat market's capacity
and the proven family's births could do to a live floor of 112-128 agents, each a scenario that failed before its fix.
"""
from __future__ import annotations

from unittest.mock import patch

from league.house import Newcomer
from league.tests.test_house import BUYER
from league.tests.test_seat_evidence import EvidenceCase


class ReviewCase(EvidenceCase):
    def resident(self, name, family="another-family", code=BUYER):
        """A paper resident of the test desk in a family of its own (`seated` puts everyone in "test-family")."""
        agent = self.house.spawn(name, family, code, reason="a resident of another family")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent


class ProvenProgramWithNoMutationLeft(ReviewCase):
    """R3 breeds a proven family's program by a House mutation of its anchor's PARAMS (`_mutated_params`). When no
    distinct valid mutation is left (no declared or standard knob, the anchor's own PARAMS outside its rules, or 64
    proposals that all repeat a living twin), the family stayed owed: its desk gave every other family's newcomer no
    seat for good (`_displaceable`'s R3 hold), and the pass asked for the desk's weakest resident and a mutation (a
    rejected `agent.mutation` row each time the registry grew) on every tick."""

    def setUp(self):
        super().setUp()
        self.rules.update(newcomer_seconds=600, proven_family_members=4)
        self.anchor = self.seated("anchor")
        self.house.evaluator.promote(self.anchor.id, 2, "test: a bunt on real money")
        self.buy(self.anchor)

    def test_a_program_with_no_mutation_left_holds_no_desk_and_is_asked_again_hourly_not_every_tick(self):
        idle = self.resident("idle")  # never trades: an evidenced newcomer's seat once its fair chance has run
        self.clock.advance(3601)
        another = Newcomer(family="another", venue="alpaca", what="a graduate of another family")
        with self.proven("test-family"), patch.object(self.house, "_mutated_params", return_value=None) as mutated:
            self.assertEqual([w["family"] for w in self.house.seat_waiters(fresh=True)["proven"]], ["test-family"])
            self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 1)
            self.assertEqual(self.house.seat_waiters(fresh=True)["proven"], [], "nothing can be bred: nothing is owed")
            self.assertIn("no distinct valid mutation", self.house._proven_programs()[0]["held"])
            self.assertEqual(self.house._weakest(self.rules, specialty=self.anchor.specialty, evidenced=True, newcomer=another).id,
                             idle.id, "its desk is not held for births that cannot be made")
            for _ in range(5):
                self.clock.advance(601)
                self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 1, "not asked again every tick")
            self.clock.advance(3600)
            self.assertIsNone(self.house._proven_births(self.rules))
            self.assertEqual(mutated.call_count, 2, "asked again an hour on: a twin's death or a new anchor may open one")
        with self.proven("test-family"):
            self.clock.advance(3601)
            child = self.house._proven_births(self.rules)
            self.assertIsNotNone(child, "a mutation found again: the family is bred first again")
            self.assertNotIn("test-family", self.house._state.get("proven_unbred") or {})

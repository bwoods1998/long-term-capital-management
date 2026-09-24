"""The Alpha Lab's part of the close-the-gaps run's seat market (Sept 24, 2026).

S2: the hourly forward windows score every living resident's current program too (their programs are
the lab's seeds), so a newcomer's forward score can be compared with the resident's own record before
the resident loses its seat. A forward window still never promotes anyone, never counts as practice
evidence and never touches the sealed holdout; residents are scored inside the run's existing budget.
"""

from __future__ import annotations

import math
from unittest.mock import patch

from league.house import Newcomer, _epoch
from league.tests.test_lab import DESK, KNOB, LOSER, SPARSE
from league.tests.test_lab_forward import ForwardCase


class ResidentWindows(ForwardCase):
    def resident(self, name="rosenfeld", code=KNOB):
        agent = self.house.spawn(name, "crypto-family", code, reason="a resident")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def test_every_living_residents_program_gets_a_forward_window(self):
        resident = self.resident()
        self.lab.seed(force=True)
        ident = self.lab.resident_candidate(resident)
        self.assertEqual(self.candidate(ident)["status"], "queued", "a seed not yet searched: in no cell and no graduation")
        head = self.house.ledger.head()[0]
        self.assertIsNone(self.lab.resident_forward(resident))
        out = self.lab.forward_windows(force=True)
        self.assertGreaterEqual(out["scored"], 1)
        record = self.lab.forward_record(ident)
        grid = float(self.lab.settings["forward_resident_cut_hours"]) * 3600
        self.assertEqual(record["window_start"], math.ceil(_epoch(resident.born_at) / grid) * grid,
                         "the window starts after its program was frozen, on the residents' grid")
        self.assertIsInstance(self.lab.resident_forward(resident), float)
        self.assertEqual(self.lab.resident_forward(resident, ranked=True), self.lab.forward_score(ident))
        # Never practice evidence: no eval, holdout or birth rows, and its standing is untouched.
        kinds = {e.kind for e in self.house.ledger.iter(after=head)}
        self.assertFalse(kinds & {"eval.trial", "eval.verdict", "eval.block", "holdout.access", "agent.born", "lab.graduate"}, kinds)
        self.assertEqual(self.house.evaluator.rung(resident.id), 1)

    def test_a_trader_the_lab_never_scores_is_not_kept_for_good(self):
        """The review of #245 (Sept 24, 2026): the lab never searches alpaca-options (`replay` false, options), so
        krasker-6, -10, -11 and -14 (3-8 fills at T0) could never have a forward record, and the forward rule kept
        their seats against every newcomer for good. While the lab CAN score a trader, it keeps its seat until
        it has a record; where it never can, the tournament judges it as before."""
        rules = self.house.game["economy"]
        trader = self.resident()
        for _ in range(3):
            self.house.ledger.append("book.fill", {"book": "alpaca-paper", "symbol": "BTC/USD", "side": "buy", "quantity": "0.001",
                                                   "price": "60000", "source": "venue", "liquidity": "taker"}, agent=trader.id)
        self.clock.advance(float(rules["epoch_seconds"]) * float(rules["displace_after_epochs"]) * 10)
        newcomer = Newcomer(forward=0.05)
        self.assertTrue(self.lab.can_score(trader))
        self.assertIsNone(self.house._weakest(rules, newcomer=Newcomer(forward=-0.05)),
                          "not scored yet: it keeps its seat until it has a record")
        # R2's S3 (Sept 24, 2026): that wait ends with its desk's evidence clock (the plain grace on a desk with none): long
        # past it, with no positive record of its own, a newcomer with a winning forward window takes the seat.
        self.assertEqual(self.house._weakest(rules, newcomer=newcomer).id, trader.id)
        self.niche.replay = False  # as alpaca-options: a desk the lab never searches
        self.assertFalse(self.lab.can_score(trader))
        self.assertEqual(self.house._weakest(rules, newcomer=Newcomer(forward=-0.05)).id, trader.id,
                         "never scorable: the tournament judges it as before, whatever the newcomer's score")
        self.niche.replay = True
        self.lab.seed(force=True)
        self.lab._x("UPDATE candidates SET status='blocked' WHERE id=?", (self.lab.resident_candidate(trader),))
        self.assertFalse(self.lab.can_score(trader), "a program the lab has blocked is never scored either")

    def test_a_rewritten_programs_window_starts_after_the_rewrite(self):
        resident = self.resident()
        self.clock.advance(8 * 3600)
        self.house.registry.adopt(resident.id, code=SPARSE, needs=resident.needs, params={"notional": 50.0}, reason="a research rewrite")
        rewritten = self.house.registry.get(resident.id)
        self.lab.seed(force=True)
        self.lab.forward_windows(force=True)
        record = self.lab.forward_record(self.lab.resident_candidate(rewritten))
        grid = float(self.lab.settings["forward_resident_cut_hours"]) * 3600
        self.assertEqual(record["window_start"], math.ceil(self.clock() / grid) * grid)

    def test_residents_are_scored_after_the_waiting_graduates_and_before_the_elites_then_oldest_first(self):
        elite = self.elite(KNOB)
        self.clock.advance(60)
        graduate = self.queue(SPARSE, lineage="founder:other")
        self.lab.evaluate_batch()
        self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                    (graduate, DESK, "founder:other", "rosenfeld-lgrad", "f", "passed", self.clock(),
                     "its desk is full of agents that have earned their seats"))
        resident = self.resident("rosenfeld", LOSER)
        self.lab.seed(force=True)
        ident = self.lab.resident_candidate(resident)
        self.assertEqual([r["id"] for r in self.lab.forward_due(3)], [graduate, ident, elite])
        self.forward_row(graduate, 0.001)
        self.clock.advance(60)
        self.forward_row(ident, 0.001)
        self.assertEqual([r["id"] for r in self.lab.forward_due(3)], [elite, graduate, ident], "then least recently scored")

    def test_a_dead_agents_program_is_not_a_resident(self):
        resident = self.resident()
        self.lab.seed(force=True)
        ident = self.lab.resident_candidate(resident)
        self.house.kill(resident, "displaced", "test")
        self.assertNotIn(ident, [r["id"] for r in self.lab.forward_due(10)])

    def test_a_graduate_asks_for_a_seat_with_its_forward_score_and_its_family(self):
        ident = self.elite(KNOB)
        self.forward_row(ident, 0.004)
        row = self.candidate(ident)
        self.niche.max_members = 1
        self.resident()
        with patch.object(self.house, "_weakest", return_value=None) as weakest:
            self.lab._seat_for(row, self.niche, self.house.game["economy"], line="rosenfeld-lx", family="crypto-majors-lab-x")
        newcomer = weakest.call_args.kwargs["newcomer"]
        self.assertEqual((newcomer.forward, newcomer.family, newcomer.venue), (0.004, "crypto-majors-lab-x", "alpaca"))


if __name__ == "__main__":
    import unittest

    unittest.main()

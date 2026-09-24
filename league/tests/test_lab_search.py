"""E1 of the close-the-gaps run (Sept 24, 2026): the Alpha Lab as a search.

The evidence (docs/goals/LTCM_CLOSE_THE_GAPS.md, gap 1): of the lab's 3,641 candidates at T0, 2,137 were
parameter mutants; 16 of the 18 born graduates were nudges (an impulse floor 0.0006 -> 0.000686); the
attention desk went 48 h without an intent and still received lab graduates; after Deploy A the lab ran 63
batches of 84 candidates in an hour, 1.3 a batch, because the Luna children at the queue's front each need
a tape of their own and a step builds four.

These tests hold: half of a batch for the programs someone wrote where they wait, and a step's builds shared
so its batches are full (`batch_turn`); graduation only for a change beyond PARAMS or a forward score above
the desk's living median, never on a losing forward window, never onto a desk idle for 48 h unless a feed it
asked for arrived since; breeding ranked by the forward window; the family ledger's record and capacity in
the search's weights; Sol's leaps on the deep-market desks first.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from league.economy import check_bounds, load_game

from league.lab import (FORWARD_BREEDING, RESERVED_SHARE_BOUNDS, batch_turn, family_at_capacity, forward_factor, mechanism_digest,
                        reserved_quota, with_params)
from league.tests.test_lab import KNOB, REWRITTEN, SMALLER, SPARSE, LabCase
from league.tests.test_lab_forward import ForwardCase

#: Programs on KNOB's own tape (a style is not part of the tape): what Luna writes when it keeps the NEEDS.
SAME_TAPE = [KNOB.replace('"style": "sawtooth"', f'"style": "written-{n}"') for n in range(12)]
#: Programs each on a tape of its own: what most Luna children are (65 of the 69 queued at T4 changed NEEDS).
OWN_TAPES = [KNOB.replace('"symbols": ["BTC/USD"]', f'"symbols": ["{symbol}"]').replace('"timeframe": "5Min"', f'"timeframe": "{frame}"')
             for symbol in ("BTC/USD", "ETH/USD") for frame in ("15Min", "1Hour", "1Day")]


class ReservedShare(LabCase):
    def test_half_of_a_batch_is_the_written_programs_where_they_wait(self):
        """A tape where older seeds and newer Luna children wait: a third (2 of 8) went to the children."""
        self.house.game["lab"]["batch_size"] = 8
        for n in range(8):  # seeds of the same tape, admitted first
            self.lab.admit(with_params(KNOB, {"notional": 10.0 + n}), niche=self.niche, origin="seed", author="house",
                           lineage=f"agent:seed-{n}")
        self.clock.advance(60)
        children = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:test")
                    for code in SAME_TAPE[:8]]
        _, _, chosen = self.lab._next_batch()
        self.assertEqual(len(chosen), 8)
        self.assertEqual([r["origin"] for r in chosen].count("luna"), 4)
        self.assertEqual({r["id"] for r in chosen[:4]} <= set(children), True)

    def test_the_share_is_held_to_its_bounds(self):
        self.assertEqual(RESERVED_SHARE_BOUNDS, (0.33, 0.75))
        self.assertEqual(reserved_quota(32, 0.5), 16)
        self.assertEqual(reserved_quota(32, 0.9), 24)  # 0.75 at most
        self.assertEqual(reserved_quota(32, 0.1), 11)  # 0.33 at least
        self.assertEqual(reserved_quota(3, 0.5), 2)
        self.assertEqual(reserved_quota(32, "nonsense"), 11)


class FullBatches(LabCase):
    def test_the_turns_share_the_builds(self):
        """Half of the turns (the reserved share) serve the written programs; the rest alternate between the
        queue's oldest row and the largest group of any origin."""
        turns = [batch_turn(t, 0.5) for t in range(1, 9)]
        self.assertEqual(turns, ["queue", "reserved", "largest", "reserved"] * 2)
        self.assertEqual([batch_turn(t, 0.75) for t in range(1, 9)].count("reserved"), 6)
        self.assertEqual([batch_turn(t, 0.33) for t in range(1, 10)].count("reserved"), 3)

    def test_a_step_builds_the_mutants_tape_while_written_programs_wait_each_on_a_tape_of_its_own(self):
        """After Deploy A the step's four builds all went to Luna children a tape each (1.3 a batch) while the
        archive's mutants waited dozens to a tape. Now one build in four is the largest group's."""
        elite = self.queue(KNOB)
        self.lab.evaluate_batch()  # its tape built
        mutants = [self.lab.admit(with_params(KNOB, {"notional": 10.0 + n}), niche=self.niche, origin="param", author="house",
                                  lineage="founder:test", parents=[elite]) for n in range(24)]
        self.clock.advance(60)
        written = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:test", parents=[elite])
                   for code in OWN_TAPES]
        self.lab._tapes.clear()  # a restart: every tape must be built again
        self.lab._tapes_built = 0  # one step: four builds
        sizes = []
        while True:
            done = self.lab.evaluate_batch()
            if not done:
                break
            sizes.append(done["candidates"])
        self.assertEqual(self.lab._tapes_built, 4)
        self.assertIn(24, sizes, sizes)  # the mutants ran whole, in the step
        self.assertEqual([self.candidate(m)["status"] for m in mutants].count("queued"), 0)
        self.assertEqual(sum(self.candidate(w)["status"] != "queued" for w in written), 3, sizes)  # and three of the six
        self.assertGreater(sum(sizes) / self.lab._tapes_built, 1.3)

    def test_the_written_programs_turn_builds_the_tape_most_candidates_wait_on(self):
        """Grouped by tape: of the written programs, the tape with the most rows waiting is built first."""
        lone = self.lab.admit(OWN_TAPES[0], niche=self.niche, origin="luna", author="luna", lineage="founder:a")
        self.clock.advance(60)
        grouped = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:b")
                   for code in SAME_TAPE[:3]]
        self.lab._batch_turn = 1  # the next turn is the written programs'
        _, _, chosen = self.lab._next_batch()
        self.assertEqual({r["id"] for r in chosen}, set(grouped))
        self.assertEqual(self.candidate(lone)["status"], "queued")



class Bounds(unittest.TestCase):
    def test_the_game_file_holds_the_labs_bounded_dials(self):
        game = load_game()
        check_bounds(game)
        self.assertEqual((game["lab"]["reserved_share"], game["lab_bounds"]["reserved_share"]), (0.5, [0.33, 0.75]))
        self.assertEqual(game["lab"]["idle_desk_hours"], 48)
        self.assertIn("alpaca-megacaps", game["lab"]["deep_desks"])
        bad = copy.deepcopy(game)
        bad["lab"]["reserved_share"] = 0.9
        with self.assertRaisesRegex(ValueError, "lab.reserved_share"):
            check_bounds(bad)


class PracticeSizing(unittest.TestCase):
    def test_practice_agents_are_told_that_a_conviction_sized_record_earns_the_familys_proof_sooner(self):
        """C3 (Sept 24, 2026): the rules text, never a forced size."""
        from league.rules import rules_text

        text = " ".join(rules_text(load_game()).split())
        self.assertIn("What proves (or disproves) a family faster is MORE independent events, and CONVICTION", text)
        self.assertIn("a conviction-sized practice record earns your family's proof sooner than one flat size when the "
                      "conviction is real, and disproves it sooner when it is not", text)
        self.assertIn("This is information, never an order: your size is your code's.", text)
        self.assertEqual(text.count("SIZE ON PRACTICE IS YOURS"), 1)  # said once, beside the family's pooled proof
        self.assertNotIn("paper", text[text.index("SIZE ON PRACTICE"):text.index("never an order")].lower())


class Mechanism(unittest.TestCase):
    def test_a_parameter_change_is_the_same_mechanism_and_a_code_change_is_not(self):
        base = mechanism_digest(KNOB)
        self.assertIsNotNone(base)
        self.assertEqual(mechanism_digest(with_params(KNOB, {"notional": 12.5})), base)
        self.assertEqual(mechanism_digest(SMALLER), base)  # what the lab's Luna fake writes: a nudge
        restyled = KNOB.replace('"style": "sawtooth"', '"style": "bolder"').replace(
            "def decide(ctx):", 'def decide(ctx):\n    """Buy the dip, said differently."""  # and a comment')
        self.assertEqual(mechanism_digest(restyled), base)
        self.assertNotEqual(mechanism_digest(SPARSE), base)  # another entry rule
        self.assertNotEqual(mechanism_digest(KNOB.replace('"symbols": ["BTC/USD"]', '"symbols": ["ETH/USD"]')), base)  # other data
        self.assertIsNone(mechanism_digest("def decide(ctx:\n"))


class Holds(ForwardCase):
    """16 of the 18 graduates born by T0 were nudges of a living program."""

    def setUp(self):
        super().setUp()
        self.resident = self.seated("resident", KNOB)  # a living program of the desk

    def nudge(self):
        ident = self.elite(with_params(KNOB, {"notional": 30.0}), origin="param", lineage=f"agent:{self.resident.id}")
        self.assertTrue(self.candidate(ident)["gate"])
        return ident

    def test_a_nudge_of_a_living_program_is_held_and_not_tried(self):
        self.nudge()
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._q("SELECT * FROM graduations"), [])  # not a trial, not refused: it may graduate later
        self.assertEqual(self.lab._held["counts"], {"nudge": 1})
        self.assertEqual(self.lab.stats()["held"]["counts"], {"nudge": 1})
        self.assertEqual(self.lab.health()["held"]["counts"], {"nudge": 1})

    def test_a_cell_whose_elite_is_a_nudge_graduates_the_next_program_of_the_cell(self):
        """Graduating only the elite, a cell whose fittest program on the search tape was a parameter nudge never
        graduated the mechanism change beside it."""
        rewritten = self.elite(REWRITTEN, origin="luna", lineage=f"agent:{self.resident.id}")
        nudge = self.nudge()
        cell = self.candidate(nudge)["cell"]
        self.assertEqual(self.candidate(rewritten)["cell"], cell)
        self.lab._x("UPDATE candidates SET fitness=1.0 WHERE id=?", (nudge,))  # the fittest of the cell: its elite
        self.lab._x("UPDATE archive SET candidate=?, fitness=1.0 WHERE cell=?", (nudge, cell))
        self.assertEqual([r["id"] for r in self.lab.elites()], [nudge])
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (rewritten, "born"))
        self.assertEqual(self.lab._held["counts"], {"nudge": 1})

    def test_a_code_change_graduates_without_a_forward_score(self):
        child = self.elite(SPARSE, origin="luna", lineage=f"agent:{self.resident.id}")
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (child, "born"))

    def test_a_nudge_graduates_with_a_forward_score_above_the_desks_living_median(self):
        nudge = self.nudge()
        self.forward_row(self.lab.resident_candidate(self.resident), 0.004)  # the resident's own window: the median
        self.forward_row(nudge, 0.003)
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"nudge": 1})
        self.clock.advance(1)
        self.forward_row(nudge, 0.006)
        self.assertEqual(self.lab.graduate()[0]["state"], "born")

    def test_on_a_desk_whose_residents_have_no_forward_score_a_nudge_needs_a_winning_window_of_its_own(self):
        nudge = self.nudge()
        self.assertIsNone(self.lab._desk_median(self.niche.id))
        self.assertEqual(self.lab.graduate(), [])
        self.forward_row(nudge, 0.001)
        self.assertEqual(self.lab.graduate()[0]["state"], "born")

    def test_a_losing_forward_window_holds_a_candidate_whatever_its_search_fitness(self):
        child = self.elite(SPARSE, origin="luna", lineage=f"agent:{self.resident.id}")
        self.forward_row(child, -0.002)
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"forward": 1})
        self.clock.advance(1)
        self.forward_row(child, 0.002)
        self.assertEqual(self.lab.graduate()[0]["state"], "born")

    def test_no_graduate_onto_a_desk_offered_markets_with_no_intent_unless_a_feed_it_asked_for_arrived(self):
        """The attention desk went 48 h without an intent at T0 and still received lab graduates."""
        self.elite(SPARSE, origin="luna", lineage="founder:new")
        self.house.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "offered": 3}, agent=self.resident.id)
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"idle": 1})
        asked = self.house.ledger.append("tool.request", {"name": "btc_perp_funding_history", "description": "funding"},
                                         agent=self.resident.id)
        self.house.ledger.append("tool.fulfilled", {"request": asked.id, "outcome": "Shipped", "change": "league/feeds.py"})
        self.clock.advance(601)  # a desk's idleness is read every ten minutes
        self.assertEqual(self.lab.graduate()[0]["state"], "born")

    def test_a_desk_that_traded_or_was_offered_nothing_is_not_idle(self):
        self.assertIsNone(self.lab._idle_desk(self.niche.id))  # offered nothing: the calendar's doing
        self.house.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "offered": 3}, agent=self.resident.id)
        self.house.ledger.append("agent.intent", {"book": "alpaca-paper", "side": "buy"}, agent=self.resident.id)
        self.clock.advance(601)
        self.assertIsNone(self.lab._idle_desk(self.niche.id))
        self.clock.advance(49 * 3600)
        self.house.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "offered": 2}, agent=self.resident.id)
        self.assertIn("wrote no intent in 48 h", self.lab._idle_desk(self.niche.id))

    def test_a_graduate_waiting_for_a_seat_is_held_before_its_birth(self):
        nudge = self.nudge()
        self.forward_row(nudge, 0.004)
        self.niche.max_members = 1  # the resident fills the desk
        with patch.object(self.house, "_weakest", return_value=None):
            self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        self.clock.advance(601)
        self.forward_row(nudge, -0.001)  # its window turned
        out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "held")
        row = self.lab._q("SELECT state, detail FROM graduations WHERE candidate=?", (nudge,))[0]
        self.assertEqual(row["state"], "passed")
        self.assertTrue(row["detail"].startswith("held: forward"), row["detail"])
        self.assertEqual(self.lab.waiting(), [])  # it reserves no seat
        self.assertEqual(self.house.ledger.get(f"lab.graduate:{nudge}:held").payload["state"], "held")


class Search(ForwardCase):
    def record(self, state="unproven", **extra):
        return {"family": "test-family", "venue": "alpaca", "state": state, "n": 12, "mean_log": 0.01,
                "rule": {"min_independent_settlements": 10}, **extra}

    def test_the_family_ledger_weighs_a_lineage_and_capacity_stops_its_search(self):
        grown = self.seated("grown", KNOB)
        mine = self.elite(SPARSE, lineage=f"agent:{grown.id}")
        other = self.elite(KNOB, lineage="founder:other")
        with patch.object(self.house.allocator, "family", return_value=self.record("proven")):
            self.lab._weights = None
            self.assertEqual(self.lab.lineage_weights()[f"agent:{grown.id}"], 2.0)  # a proven family: +1
        with patch.object(self.house.allocator, "family", return_value=self.record(n=12, mean_log=-0.01)):
            self.lab._weights = None
            self.assertEqual(self.lab.lineage_weights()[f"agent:{grown.id}"], 0.5)  # negative past the proof's count
        full = self.record("swing", swing={"limit": "capacity"})
        with patch.object(self.house.allocator, "family", return_value=full):
            self.lab._weights = None
            self.assertEqual(self.lab.lineage_weights()[f"agent:{grown.id}"], 0.0)
            picked = {self.lab._pick_parent()["id"] for _ in range(20)}
        self.assertEqual(picked, {other})  # no more search on a family at its capacity
        self.assertNotIn(mine, picked)

    def test_capacity_is_read_from_the_family_ledger(self):
        rule = {"capacity_fill_ratio": 0.5, "capacity_min_markets": 5}
        rates = {"<=$12": {"markets_bid": 20, "fill_rate": 0.6}, "$12-25": {"markets_bid": 6, "fill_rate": 0.2}}
        self.assertTrue(family_at_capacity({"capacity": {"size_usd": 10.0, "fill_rates": rates}}, rule))
        rates["$12-25"]["fill_rate"] = 0.5
        self.assertFalse(family_at_capacity({"capacity": {"size_usd": 10.0, "fill_rates": rates}}, rule))
        self.assertFalse(family_at_capacity({"capacity": {"size_usd": 10.0, "fill_rates": {}}}, rule))  # never measured
        self.assertTrue(family_at_capacity({"swing": {"limit": "capacity"}}, None))
        self.assertFalse(family_at_capacity(None, rule))

    def test_breeding_ranks_by_the_parents_own_forward_window(self):
        winner, loser = self.elite(KNOB, lineage="founder:a"), self.elite(SPARSE, lineage="founder:b")
        self.forward_row(winner, 0.003)
        self.forward_row(loser, -0.003)
        lineages = self.lab.lineage_weights()
        seen = {}

        def choices(rows, weights, k):
            seen.update({r["id"]: w for r, w in zip(rows, weights)})
            return [rows[0]]

        with patch.object(self.lab._rng, "choices", side_effect=choices):
            self.lab._pick_parent()
        self.assertEqual(seen[winner], lineages["founder:a"] * FORWARD_BREEDING[0])
        self.assertEqual(seen[loser], lineages["founder:b"] * FORWARD_BREEDING[1])
        self.assertEqual((forward_factor(None), forward_factor(0.0)), (1.0, FORWARD_BREEDING[1]))

    def test_sol_leaps_on_the_deep_market_desks_first(self):
        self.house.game["lab"]["deep_desks"] = ["alpaca-index-etfs"]
        for _ in range(3):
            self.lab.leap()
        self.assertEqual({asked["user"]["desk"]["id"] for asked in self.sol.asked}, {"alpaca-index-etfs"})


if __name__ == "__main__":
    unittest.main()

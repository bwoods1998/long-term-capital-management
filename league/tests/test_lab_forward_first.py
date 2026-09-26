"""F1 of the forward-first run (Sept 25, 2026): the Alpha Lab breeds, places and graduates on forward growth.

The evidence (docs/goals/LTCM_FORWARD_FIRST.md, gap 2, and the T0 snapshot of 04:21Z Sept 25): the archive placed
every cell by search fitness (`Lab._place`) while the forward windows only ranked; 273 candidates went to the House's
replay in 24 h (446 `lab.graduate` rows, 17% of the candidates written by Luna, Sol or an agent) and 2 of them had a
winning forward window of their own when they went; 11 lineages whose latest window lost over six or more active
blocks were still bred. Re-placing the T0 archive by the lineages' forward records moves 44 of its 83 cells, and the
elites of lineages with a winning record go from 15 to 46.

These tests hold: a lineage with a record is placed and ordered by it and search fitness places only the lineages
without one (replay still admits: a program that failed the gate is placed by fitness); the archive is re-placed after
every forward run; a lineage whose latest window loses over six active blocks is neither bred nor graduated until a
later window wins; a candidate graduates only on a winning window of its own where the lab can build one, and the
forward runs score the ones graduation waits for first, mechanism children first; where no window can be built, only
a code change beyond PARAMS graduates; and the mechanism children take two thirds of each batch and of the turns.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from unittest.mock import patch

from league.economy import check_bounds, load_game
from league.lab import LabError, batch_turn, forward_rank, lineage_block, mechanism_share, reserved_quota, tape_key, with_params
from league.tests.test_lab import DESK, KNOB, REWRITTEN, SPARSE
from league.tests.test_lab_forward import ForwardCase
from league.tests.test_lab_search import SAME_TAPE


class Rules(unittest.TestCase):
    def test_a_lineages_forward_record_places_before_search_fitness(self):
        winning, untested, losing = forward_rank(0.0001, None, 0.002), forward_rank(0.5, None, None), forward_rank(0.9, 0.01, -0.001)
        self.assertLess(winning, untested)
        self.assertLess(untested, losing)
        self.assertLess(forward_rank(0.0, None, 0.003), forward_rank(0.0, None, 0.002))  # by growth per block
        self.assertLess(forward_rank(0.1, None, None), forward_rank(0.05, None, None))  # fitness between lineages without one
        # Within a lineage its program's own window decides, never search fitness: a tie keeps the incumbent.
        self.assertLess(forward_rank(0.0, 0.001, 0.002), forward_rank(0.9, None, 0.002))
        self.assertLess(forward_rank(0.0, None, 0.002), forward_rank(0.9, -0.001, 0.002))
        self.assertEqual(forward_rank(0.1, None, 0.002), forward_rank(0.9, None, 0.002))
        # Replay admits: a program that did not pass the gate is placed by its fitness whatever its lineage's record
        # (T0: a mutant losing 0.177 a block on the search tape, on a lineage at +0.027).
        self.assertEqual(forward_rank(-0.177, None, 0.027, admitted=0), forward_rank(-0.177, None, None))
        self.assertLess(forward_rank(0.01, None, None), forward_rank(-0.177, None, 0.027, admitted=False))
        # ... but a losing record counts against it (the review of #306): after every program that passed the gate, its own
        # losing lineage's included (T0: 097632d172, gate 0, took its cell from ec93164b9d, both haghani-39).
        self.assertLess(forward_rank(0.001, None, -0.001), forward_rank(-0.0005, None, -0.001, admitted=0))
        self.assertLess(forward_rank(0.9, -0.01, -0.5), forward_rank(0.9, None, -0.001, admitted=0))

    def test_a_lineage_is_blocked_by_a_window_losing_over_six_active_blocks_until_a_later_one_wins(self):
        def window(start, at, growth, active):
            return {"candidate": f"c{start}", "window_start": start, "at": at, "log_growth": growth, "active_blocks": active,
                    "blocks": active + 2}

        rule = {"min_active": 3, "block_active": 6}
        self.assertIsNone(lineage_block([], **rule))
        self.assertIsNone(lineage_block([window(0, 10, -0.05, 5)], **rule))  # five active blocks: not yet
        self.assertEqual(lineage_block([window(0, 10, -0.05, 6)], **rule)["candidate"], "c0")
        # A window on later data that wins clears it, whenever it was scored ...
        self.assertIsNone(lineage_block([window(0, 10, -0.05, 6), window(3600, 5, 0.01, 3)], **rule))
        # ... never one on earlier data, one too short to rank, or one that loses too.
        self.assertIsNotNone(lineage_block([window(3600, 10, -0.05, 8), window(0, 20, 0.01, 3)], **rule))
        self.assertIsNotNone(lineage_block([window(0, 10, -0.05, 8), window(3600, 20, 0.01, 2)], **rule))
        self.assertIsNotNone(lineage_block([window(0, 10, -0.05, 8), window(3600, 20, -0.01, 4)], **rule))

    def test_the_mechanism_children_take_two_thirds_and_the_parameter_children_keep_a_third(self):
        self.assertEqual(mechanism_share(0.33), 0.67)
        self.assertEqual(reserved_quota(32, 0.33), 22)
        self.assertEqual(reserved_quota(32, 0.5), 16)  # E1's half is the same batch in either reading
        self.assertEqual(reserved_quota(32, 0.75), 8)
        self.assertEqual(reserved_quota(32, 0.1), 22)  # held to its bounds
        self.assertEqual([batch_turn(t, 0.33) for t in range(1, 7)], ["reserved", "reserved", "queue", "reserved", "reserved", "largest"])
        self.assertEqual([batch_turn(t, 0.5) for t in range(1, 5)], ["queue", "reserved", "largest", "reserved"])

    @unittest.skip('Wave 2b deletes the Alpha Lab: the options overhaul (Sept 26, 2026) took its game.json block out')
    def test_the_game_file_carries_the_dials_inside_their_bounds(self):
        game = load_game()
        check_bounds(game)
        self.assertEqual((game["lab"]["reserved_share"], game["lab_bounds"]["reserved_share"]), (0.33, [0.33, 0.75]))
        self.assertEqual((game["lab"]["lineage_block_active_blocks"], game["lab"]["forward_box_seconds"],
                          game["lab"]["forward_candidates_per_run"]), (6, 180, 96))
        for key, value in (("lineage_block_active_blocks", 2), ("forward_box_seconds", 900), ("forward_candidates_per_run", 500)):
            bad = copy.deepcopy(game)
            bad["lab"][key] = value
            with self.assertRaisesRegex(ValueError, f"lab.{key}"):
                check_bounds(bad)


class FirstCase(ForwardCase):
    def window(self, ident, mean, *, active=5, blocks=6, start=None, ok=1):
        """One forward row for `ident`, scored now, on data from `start` (an hour ago by default)."""
        start = self.clock() - 3600 if start is None else start
        self.lab._x("INSERT INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                    " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident, self.clock(), start, self.clock(), "fwd:test", ok, blocks, active, mean * blocks, mean, 4,
                     None if ok else "a test failure"))
        self.lab._weights = None
        self.clock.advance(1)

    def cell_of(self, ident):
        return self.candidate(ident)["cell"]

    def elite_of(self, cell):
        return self.lab._q("SELECT candidate FROM archive WHERE cell=?", (cell,))[0]["candidate"]


class Placement(FirstCase):
    def test_a_lineage_with_a_winning_record_keeps_its_cell_against_a_fitter_program_without_one(self):
        """Before F1 the fitter program took the cell: search fitness placed every cell."""
        mine = self.elite(KNOB, lineage="founder:a")
        self.window(mine, 0.002)
        fitter = self.elite(with_params(KNOB, {"notional": 60.0}), origin="param", lineage="founder:b")
        cell = self.cell_of(mine)
        self.assertEqual(self.cell_of(fitter), cell)
        self.assertGreater(self.candidate(fitter)["fitness"], self.candidate(mine)["fitness"])
        self.assertEqual(self.elite_of(cell), mine)

    def test_a_lineage_with_a_losing_record_loses_its_cell_to_a_less_fit_program_without_one(self):
        mine = self.elite(KNOB, lineage="founder:a")
        self.window(mine, -0.002)
        weaker = self.elite(with_params(KNOB, {"notional": 40.0}), origin="param", lineage="founder:b")
        self.assertLess(self.candidate(weaker)["fitness"], self.candidate(mine)["fitness"])
        self.assertEqual(self.elite_of(self.cell_of(mine)), weaker)

    def test_a_sibling_never_takes_the_cell_on_search_fitness_and_a_program_the_gate_refused_is_placed_by_fitness(self):
        mine = self.elite(KNOB, lineage="founder:a")
        self.window(mine, 0.002)
        sibling = self.elite(with_params(KNOB, {"notional": 60.0}), origin="param", lineage="founder:a")
        cell = self.cell_of(mine)
        self.assertEqual(self.elite_of(cell), mine)  # the lineage's record cannot tell them apart: the incumbent stays
        # Without a record the fitter program takes the cell, as every cell was placed before.
        self.lab._x("DELETE FROM forward")
        self.assertTrue(self.lab._place(cell, DESK, sibling, float(self.candidate(sibling)["fitness"])))
        self.assertEqual(self.elite_of(cell), sibling)
        # A program the gate refused is placed by its search fitness, never by its lineage's record: a sibling that
        # passed takes the cell from it, although the incumbent has a winning window of its own.
        self.window(mine, 0.002)
        self.lab._x("UPDATE archive SET candidate=?, fitness=? WHERE cell=?", (mine, -0.5, cell))
        self.lab._x("UPDATE candidates SET gate=0 WHERE id=?", (mine,))
        self.assertTrue(self.lab._place(cell, DESK, sibling, float(self.candidate(sibling)["fitness"])))
        self.assertEqual(self.elite_of(cell), sibling)

    def test_the_archive_is_re_placed_and_ordered_by_the_lineages_records_as_they_arrive(self):
        first = self.elite(KNOB, lineage="founder:a")
        second = self.elite(with_params(KNOB, {"notional": 40.0}), origin="param", lineage="founder:b")
        other = self.elite(SPARSE, origin="luna", lineage="founder:c")
        cell = self.cell_of(first)
        self.assertEqual(self.elite_of(cell), first)  # placed by search fitness: no record yet
        self.assertNotEqual(self.cell_of(other), cell)
        self.window(first, -0.003)  # founder:a loses, founder:b wins, founder:c has no record
        self.window(second, 0.001)
        out = self.lab.replace_archive()
        self.assertEqual((out["moved"], out["by_forward_record"]), (1, 1))
        self.assertEqual(self.elite_of(cell), second)
        self.assertEqual([r["id"] for r in self.lab.elites()], [second, other])
        self.assertEqual(self.lab.replace_archive()["moved"], 0)  # nothing new: nothing moves
        self.assertEqual(self.lab.stats()["forward"]["placement"]["cells"], 2)
        self.assertEqual(self.lab.stats()["forward"]["lineages"], {"with_record": 2, "winning": 1, "blocked": 0})

    def test_a_forward_run_that_scores_re_places_the_archive(self):
        self.elite(KNOB, lineage="founder:a")
        self.elite(SPARSE, origin="luna", lineage="founder:c")
        out = self.lab.forward_windows(force=True)
        self.assertEqual(out["scored"], 2)
        self.assertEqual(out["placement"]["cells"], 2)
        self.assertEqual(self.lab.stats()["forward"]["placement"], out["placement"])


class LineageRule(FirstCase):
    def test_a_lineage_losing_over_six_active_blocks_is_neither_bred_nor_graduated_until_a_later_window_wins(self):
        loser = self.elite(SPARSE, origin="luna", lineage="founder:a")
        started = self.clock() - 3600
        self.window(loser, -0.002, active=6, blocks=8, start=started)
        self.assertEqual(self.lab.lineage_weights()["founder:a"], 0.0)
        self.assertIsNone(self.lab._pick_parent())  # the only elite is not drawn
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"lineage": 1})
        self.assertIn("neither bred nor graduated", self.lab._hold(self.candidate(loser)))
        self.assertEqual(self.lab.stats()["forward"]["lineages"]["blocked"], 1)
        # A child of the lineage whose window, on later data, wins: the lineage is bred and graduates again.
        child = self.elite(REWRITTEN.replace("< 79999", "< 79998"), origin="luna", lineage="founder:a")
        self.window(child, 0.003, active=3, start=started + 3600)
        self.assertGreater(self.lab.lineage_weights()["founder:a"], 0.0)
        self.assertIsNotNone(self.lab._pick_parent())
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (child, "born"))

    def test_a_blocked_lineage_is_shown_to_luna_never_bred_as_a_partner(self):
        blocked = self.elite(SPARSE, origin="luna", lineage="founder:a")
        self.window(blocked, -0.002, active=6, blocks=8)
        parent = self.elite(KNOB, lineage="founder:b")
        with patch.object(self.lab._rng, "random", return_value=0.0):
            self.lab.mutate_llm()
        packet = self.luna.asked[-1]["user"]
        self.assertEqual(packet["parent"]["id"], parent)
        self.assertIsNone(packet["partner"])
        self.assertEqual([n["id"] for n in packet["neighbours"]], [blocked])


class Graduation(FirstCase):
    def test_a_candidate_waits_for_a_winning_window_of_its_own_and_is_scored_first(self):
        """Before F1 a code change graduated on its search fitness alone (`test_lab_search`, Sept 24)."""
        child = self.elite(SPARSE, origin="luna", lineage="founder:new")
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"pending": 1})
        self.assertEqual(self.lab._q("SELECT * FROM graduations"), [])  # not tried, not refused
        self.assertEqual(self.lab.forward_wanted(), [child])
        self.assertEqual([r["id"] for r in self.lab.forward_due(4)], [child])
        self.assertEqual(self.lab.stats()["forward"]["wanted"], 1)
        self.window(child, 0.002, active=2)  # too few active blocks to rank: still waiting
        self.assertEqual(self.lab.graduate(), [])
        self.assertIn("2 active of 6 blocks so far", self.lab._hold(self.candidate(child)))
        self.window(child, 0.002, active=3)
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (child, "born"))

    def test_a_losing_window_or_one_that_barely_trades_is_held_and_no_longer_asked_for(self):
        loser, sitter = self.elite(SPARSE, origin="luna", lineage="founder:a"), self.elite(KNOB, origin="luna", lineage="founder:b")
        self.window(loser, -0.001, active=3)
        self.window(sitter, 0.004, active=2, blocks=24)  # `forward_pending_blocks`
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"forward": 2})
        self.assertIn("fewer than the 3 a window needs to rank", self.lab._hold(self.candidate(sitter)))
        self.assertEqual(self.lab.forward_wanted(), [])

    def test_where_no_window_can_be_built_only_a_code_change_graduates(self):
        resident = self.seated("resident", KNOB)
        nudge = self.elite(with_params(KNOB, {"notional": 30.0}), origin="param", lineage=f"agent:{resident.id}")
        child = self.elite(SPARSE, origin="luna", lineage=f"agent:{resident.id}")
        self.assertEqual(self.lab.graduate(), [])
        self.assertEqual(self.lab._held["counts"], {"pending": 2})
        with patch.object(self.lab, "_forward_tape", side_effect=LabError("no live tape carries options features for a forward window")):
            out = self.lab.forward_windows(force=True)
        self.assertEqual(out["scored"], 0)
        self.assertEqual(self.lab.stats()["forward"]["unavailable"], 1)
        self.assertIn("options features", self.lab._forward_unavailable(self.candidate(child)))
        self.assertIn("only with a code change", self.lab._hold(self.candidate(nudge)))
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (child, "born"))
        # A tape the run builds again is available again: the nudge is judged by a window of its own, as everyone is.
        self.clock.advance(3601)
        self.lab.forward_windows(force=True)
        self.assertEqual(self.lab.stats()["forward"]["unavailable"], 0)
        self.assertIsNone(self.lab._forward_unavailable(self.candidate(nudge)))

    def test_the_forward_runs_are_asked_for_one_mechanism_child_and_one_other_a_cell_mechanism_children_first(self):
        params = [self.elite(with_params(KNOB, {"notional": 30.0 + n}), origin="param", lineage="founder:a") for n in range(2)]
        written = [self.elite(code, origin="luna", lineage="founder:a") for code in SAME_TAPE[:2]]
        self.assertEqual(len({self.cell_of(i) for i in params + written}), 1)
        self.lab.graduate()
        wanted = self.lab.forward_wanted()
        self.assertEqual(len(wanted), 2)
        self.assertIn(wanted[0], written)
        self.assertIn(wanted[1], params)
        self.house.game["lab"]["forward_wanted_max"] = 1
        self.lab.graduate()
        self.assertEqual(len(self.lab.forward_wanted()), 1)
        self.assertIn(self.lab.forward_wanted()[0], written)

    def test_the_order_of_the_forward_runs(self):
        """Never-scored waiting graduates, then the candidates graduation waits for, then the residents, then the
        waiting and wanted ones whose window does not rank yet, then the other never-scored, then the rest."""
        elite = self.elite(KNOB, lineage="founder:a")
        waiting = self.elite(with_params(KNOB, {"notional": 31.0}), origin="param", lineage="founder:b")
        wanted = self.elite(with_params(KNOB, {"notional": 32.0}), origin="param", lineage="founder:c")
        young = self.elite(with_params(KNOB, {"notional": 33.0}), origin="param", lineage="founder:d")
        scored = self.elite(SPARSE, origin="luna", lineage="founder:e")
        elite = self.elite_of(self.cell_of(elite))
        self.assertNotIn(elite, (waiting, wanted, young))
        self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                    (waiting, DESK, "founder:b", "rosenfeld-lwait", "f", "passed", self.clock(), "passed the House's replay"))
        self.lab._set_meta("forward_wanted", json.dumps([wanted, young]))
        self.window(young, 0.001, active=1)
        self.window(scored, 0.001, active=4)
        self.clock.advance(3600)  # a block has closed since `young` was scored (the review of #306: not before)
        self.assertEqual([r["id"] for r in self.lab.forward_due(10)], [waiting, wanted, young, elite, scored])

    def test_a_passer_keeps_the_window_that_let_it_through_and_one_without_is_held_before_its_birth(self):
        child = self.elite(SPARSE, origin="luna", lineage="founder:new")
        self.window(child, 0.002, active=3)
        self.addCleanup(setattr, self.niche, "max_members", self.niche.max_members)
        self.niche.max_members = 0  # no room on the desk
        with patch.object(self.house, "_weakest", return_value=None):
            self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        self.clock.advance(601)
        self.window(child, 0.0, active=0, blocks=1, start=self.clock())  # the window cut after its pass: young
        self.assertIsNone(self.lab.forward_score(child))
        with patch.object(self.house, "_weakest", return_value=None):
            self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")  # not held
        # A passer from before F1, with no window of its own ever, is held before its birth until one wins.
        self.lab._x("DELETE FROM forward")
        self.clock.advance(601)
        out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "held")
        self.assertTrue(self.lab._q("SELECT detail FROM graduations WHERE candidate=?", (child,))[0]["detail"].startswith("held: pending"))
        self.assertEqual(self.house._waiting_graduates(), [])
        self.assertEqual(self.lab.forward_due(4)[0]["id"], child)
        self.niche.max_members = 12
        self.clock.advance(601)
        self.window(child, 0.002, active=3)
        self.assertEqual(self.lab.graduate()[0]["state"], "born")


class Deaths(FirstCase):
    def test_a_graduate_retired_because_its_desk_closed_does_not_count_against_its_lineage(self):
        """The Kalshi run's founder-seat hook (PR #308, Sept 25, 2026) retires a closed desk's practice residents with the cause
        `desk_closed`: the desk's negative record, not the agent's. Like `redundant`, it moves nothing; any other death is -1."""
        rows = []
        for name, cause in (("closed", "desk_closed"), ("spare", "redundant"), ("broke", "credits")):
            agent = self.house.spawn(name, f"lab-{name}", with_params(KNOB, {"notional": 20.0 + len(rows)}), reason="a lab graduate",
                                     founder=f"lab:founder:{name}")
            self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, agent, at, detail) VALUES(?,?,?,?,?,?,?,?,?)",
                        (name, DESK, f"founder:{name}", agent.id, agent.family, "born", agent.id, self.clock(), ""))
            self.house.kill(agent, cause, f"a test death: {cause}")
            rows.append(self.house.registry.get(agent.id))
        self.assertEqual([self.lab._floor_score(a, 3) for a in rows], [0, 0, -1])
        weights = self.lab.lineage_weights()
        self.assertEqual((weights.get("founder:closed", 1.0), weights.get("founder:spare", 1.0), weights["founder:broke"]), (1.0, 1.0, 0.5))


class Batches(FirstCase):
    def test_the_mechanism_children_are_two_thirds_of_a_batch_where_they_wait_and_the_mutants_keep_a_third(self):
        """E1 gave the written programs half of a batch (4 of 8) and the rest in queue order, where they sit ahead of the
        parameter mutants (so eight Luna children took all 8); F1 gives them two thirds first (6 of 8) and keeps the
        rest for the mutants."""
        self.house.game["lab"]["batch_size"] = 8
        for n in range(8):
            self.lab.admit(with_params(KNOB, {"notional": 10.0 + n}), niche=self.niche, origin="param", author="house", lineage="founder:a")
        self.clock.advance(60)
        children = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:a") for code in SAME_TAPE[:8]]
        _, _, chosen = self.lab._next_batch()
        self.assertEqual(len(chosen), 8)
        self.assertEqual([r["origin"] for r in chosen].count("luna"), 6)
        self.assertTrue({r["id"] for r in chosen[:6]} <= set(children))
        self.assertEqual(self.lab.stats()["reserved"], {"share": 0.33, "mechanism_share": 0.67, "evaluated": 0})

    def test_the_tape_key_of_a_refused_forward_tape_is_the_candidates(self):
        """`_forward_unavailable` reads the key the forward run keeps: the tape's, not the whole NEEDS."""
        child = self.elite(KNOB, origin="luna", lineage="founder:a")
        needs = json.loads(self.candidate(child)["needs"])
        self.lab._note_unavailable(tape_key({**needs, "style": "other"}), "a refusal")
        self.assertEqual(self.lab._forward_unavailable(self.candidate(child)), "a refusal")
        self.lab._note_unavailable(tape_key(needs), None)
        self.assertIsNone(self.lab._forward_unavailable(self.candidate(child)))


class ReviewOf306(FirstCase):
    """The review of #306 (Sept 25, 2026), on the T0 snapshot: the waiting and wanted rows (126) came before every resident
    in each forward run, which scores 8-12; a waiting graduate that never trades was scored every run for good; asks went
    to candidates already tried and never to a parameter child; a day desk's cell held one ask for 24 days; an agent's
    submissions waited for good on its own running program's losing window; a blocked lineage placed as a winning one; a
    program the gate refused escaped its losing lineage's record; and a passer was born on an older window after its
    latest one failed."""

    def test_a_resident_keeps_a_place_in_every_forward_run_whatever_waits_before_it(self):
        resident = self.seated("resident", KNOB)
        self.lab.seed(force=True)
        ident = self.lab.resident_candidate(resident)
        self.window(ident, 0.0, active=0, blocks=1)  # its first window, the hour after its birth: no active block
        wanted = [self.elite(with_params(SPARSE, {"notional": 30.0 + n}), origin="luna", lineage=f"founder:{n}") for n in range(6)]
        self.lab._set_meta("forward_wanted", json.dumps(wanted))
        for child in wanted:
            self.window(child, 0.001, active=1)  # young: scored again until they rank
        self.clock.advance(3600)
        due = [r["id"] for r in self.lab.forward_due(4)]
        self.assertEqual(due[0], ident)  # before: behind every young wanted row, so never scored again
        self.assertEqual(len(due), 4)
        self.assertLessEqual(set(due[1:]), set(wanted))

    def test_a_young_window_is_scored_again_once_a_block_closed_and_only_while_it_can_still_rank(self):
        stale = self.elite(with_params(KNOB, {"notional": 31.0}), origin="param", lineage="founder:b")
        young = self.elite(with_params(KNOB, {"notional": 32.0}), origin="param", lineage="founder:c")
        other = self.elite(SPARSE, origin="luna", lineage="founder:d")
        other = self.elite_of(self.cell_of(other))
        self.assertNotIn(other, (stale, young))
        for ident, line in ((stale, "rosenfeld-lstale"), (young, "rosenfeld-lyoung")):
            self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                        (ident, DESK, "founder:x", line, "f", "held", self.clock(), "held: pending"))
        self.window(stale, 0.0, active=1, blocks=30, start=self.clock() - 30 * 3600)  # past `forward_pending_blocks`
        self.window(young, 0.0, active=1, blocks=2)
        # The never-scored elite first: `young` was scored a minute ago, `stale` can no longer rank (before: both, every run).
        self.assertEqual([r["id"] for r in self.lab.forward_due(1)], [other])
        self.clock.advance(3600)
        self.assertEqual([r["id"] for r in self.lab.forward_due(1)], [young])
        # A day desk's window: once a day.
        self.lab._x("UPDATE candidates SET horizon='day' WHERE id=?", (young,))
        self.assertEqual([r["id"] for r in self.lab.forward_due(1)], [other])

    def test_a_candidate_tried_already_is_not_asked_for(self):
        child = self.elite(SPARSE, origin="luna", lineage="founder:new")
        self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                    (child, DESK, "founder:new", "rosenfeld-ltried", "f", "replay_failed", self.clock(), "the House's replay did not pass"))
        self.lab.graduate()
        self.assertEqual(self.lab._held["counts"], {"pending": 1})
        self.assertEqual(self.lab.forward_wanted(), [])

    def test_the_parameter_children_keep_their_share_of_the_asks(self):
        self.house.game["lab"].update({"forward_wanted_max": 2, "reserved_share": 0.75})  # one ask each at the upper bound
        mechanisms = [self.elite(REWRITTEN, origin="luna", lineage="founder:a"), self.elite(SPARSE, origin="luna", lineage="founder:b")]
        param = self.elite(with_params(KNOB, {"notional": 30.0}), origin="param", lineage="founder:c")
        self.assertEqual(len({self.cell_of(i) for i in mechanisms}), 2)
        self.lab.graduate()
        wanted = self.lab.forward_wanted()
        self.assertEqual(len(wanted), 2)
        self.assertIn(wanted[0], mechanisms)
        self.assertEqual(wanted[1], param)  # before: the two mechanism children, and never a parameter child

    def test_a_day_desks_cell_asks_the_next_program_once_the_first_has_a_day_of_data(self):
        params = [self.elite(with_params(KNOB, {"notional": 30.0 + n}), origin="param", lineage="founder:a") for n in range(4)]
        self.assertEqual(len({self.cell_of(i) for i in params}), 1)
        self.lab._x(f"UPDATE candidates SET horizon='day' WHERE id IN ({','.join('?' for _ in params)})", params)
        self.lab.graduate()
        self.assertEqual(len(self.lab.forward_wanted()), 1)  # one ask a cell and kind
        first = self.lab.forward_wanted()[0]
        self.window(first, 0.001, active=1, blocks=1, start=self.clock() - 86400)  # a day's block, one of the three it needs
        self.lab.graduate()
        wanted = self.lab.forward_wanted()
        self.assertEqual((len(wanted), wanted[0]), (2, first))  # before: `first` alone, for 24 days
        for ident in wanted[1:]:
            self.window(ident, 0.001, active=1, blocks=1, start=self.clock() - 86400)
        self.house.game["lab"]["forward_asks_per_cell"] = 3
        self.lab.graduate()
        self.assertEqual(len(self.lab.forward_wanted()), 3)
        for ident in self.lab.forward_wanted()[2:]:
            self.window(ident, 0.001, active=1, blocks=1, start=self.clock() - 86400)
        self.lab.graduate()
        self.assertEqual(len(self.lab.forward_wanted()), 3)  # at most `forward_asks_per_cell` at once

    def test_an_agents_submission_after_its_program_lost_is_asked_for_and_its_win_releases_the_lineage(self):
        resident = self.seated("resident", KNOB)
        self.lab.seed(force=True)
        seed, lineage = self.lab.resident_candidate(resident), f"agent:{resident.id}"
        self.window(seed, -0.002, active=7, blocks=8, start=self.clock() - 8 * 3600)
        self.clock.advance(3600)
        submission = self.elite(SPARSE, origin="agent", lineage=lineage)
        self.assertIn(lineage, self.lab._forward_state()["blocked"])
        self.assertEqual(self.lab.graduate(), [])
        self.assertIn("releases", self.lab._hold(self.candidate(submission)))
        self.assertEqual(self.lab.forward_wanted(), [submission])  # before: held "lineage", never scored, for good
        self.assertEqual(self.lab.lineage_weights()[lineage], 0.0)  # still not bred
        row = self.candidate(submission)
        self.window(submission, 0.003, active=3, start=math.ceil(float(row["evaluated"]) / 3600.0) * 3600.0)
        self.assertNotIn(lineage, self.lab._forward_state()["blocked"])
        out = self.lab.graduate()
        self.assertEqual((out[0]["candidate"], out[0]["state"]), (submission, "born"))

    def test_a_blocked_lineage_places_as_a_losing_one_whatever_its_pool(self):
        loser = self.elite(KNOB, lineage="founder:a")
        lucky = self.elite(with_params(KNOB, {"notional": 60.0}), origin="param", lineage="founder:a")
        other = self.elite(with_params(KNOB, {"notional": 40.0}), origin="param", lineage="founder:b")
        cell = self.cell_of(loser)
        self.assertEqual({self.cell_of(lucky), self.cell_of(other)}, {cell})
        start = self.clock() - 8 * 3600
        self.window(loser, -0.03, active=8, blocks=8, start=start)
        self.window(lucky, 0.3, active=1, blocks=1, start=start)  # one outlier block pools the lineage above zero
        self.assertIn("founder:a", self.lab._forward_state()["blocked"])
        self.lab.replace_archive()
        self.assertEqual(self.elite_of(cell), other)  # before: founder:a, placed first on +0.0067 a block
        self.assertEqual(self.lab.stats()["forward"]["lineages"], {"with_record": 1, "winning": 0, "blocked": 1})

    def test_a_passer_is_not_born_on_an_older_window_after_its_latest_one_failed(self):
        child = self.elite(SPARSE, origin="luna", lineage="founder:new")
        self.window(child, 0.002, active=3)
        self.assertIsNone(self.lab._hold(self.candidate(child)))
        self.window(child, 0.0, active=0, blocks=0, ok=0)  # the window cut after its pass raised on the new data
        self.assertIn("forward: its latest forward window failed", self.lab._hold(self.candidate(child)) or "")


if __name__ == "__main__":
    unittest.main()

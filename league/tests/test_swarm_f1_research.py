"""F1's research stream (Oct 3, 2026): the restart made to last, each rule on the real `SwarmStore`.

Research stood still from 01:35Z Oct 3: every architect proposal was refused (the request listed cells no birth could
land in and hid the ones with room), the eight living families were parked until news and none could retire (eight was
the floor), and one architect pass paused every researcher for an hour. These tests pin what F1 changes:

- THE BIRTH CELLS: the architect's request lists every cell of the allowed structure family, and no other;
- NO PAID PASS WITHOUT A CELL: a pass no cell could bear in asks no model and is recorded as skipped;
- the settings as code (the cell budget, the revision limit, each new switch with its default);
- PARKED DORMANCY: a park until news counts toward the dormancy clause with `researcher.hold_until_news` left true;
- THE FLOOR COUNTS RESEARCH: dead slots leave at the floor, a researching family does not;
- the architect's own spend is out of the researchers' hourly pace;
- THE GYM'S ROOTS: a WHERE TO LOOK section that names a ticker the Gym does not hold is refused;
- THE DEPTH RULE and AN IDENTICAL PROGRAM IS VALIDATED ONCE.

Synthetic families, mechanisms, sections and figures only."""

from __future__ import annotations

import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.swarm import cards
from league.swarm import settings as S
from league.swarm.architect import (AGENDA_KEY, BIRTH_CELLS_CHARS, FOREIGN_ROOTS_NOTE, SKIPPED_CEILING, SKIPPED_NO_CELL,
                                    Architect, tag_of)
from league.swarm.loop import PARKED_EVERY, Scheduler, Swarm, architect_spent
from league.swarm.practice import KEEP_KV, KEEP_KV_SECONDS
from league.swarm.researcher import (VALIDATED_CYCLES_KEY, Researcher, checks_met, dead_slot, dormant_count, floor_counts,
                                     idle_cause, idle_dead, short_dead, short_left)
from league.swarm.seeds import SEEDS, family_spec
from league.swarm.store import SwarmStore
from league.swarm.strategist import check_section, foreign_roots
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.swarm_fakes import Clock, result
from league.tests.test_swarm_cards import CARD, Case as CardCase
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import FakeGymPool, RoundCase, strong, weak
from league.tests.test_swarm_store import SPEC
from league.tests.test_swarm_strategist import CITES, CLEAN, FakeRouter, StrategistCase, reply

ALLOWED = ["debit_vertical", "long_single"]
GRID = {f"{c} / directional / {h}" for c in cards.MECHANISM_CLASSES for h in cards.HOLDING}
TREND = {**CARD, "mechanism_class": "trend_momentum", "holding": "days_4_10",
         "hypothesis": "Slow capital extends a trend for several sessions after a breakout and the option market underprices "
                       "the continuation."}


class Asked:
    """A router that records what it was asked and answers nothing (the pass then reports an error, never a birth)."""

    def __init__(self):
        self.calls: list[dict] = []

    def ask(self, **kw):
        self.calls.append(kw)
        raise RuntimeError("no model in this test")


# ------------------------------------------------------------------------------------------------ 1. the birth cells
class BirthCells(CardCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"].update(structures=list(ALLOWED), claimable_rows=2, max_rebirths_per_cell=2)

    def card(self, raw=CARD):
        card, errors = cards.validate(raw)
        self.assertEqual(errors, [])
        return card

    def test_the_request_lists_every_cell_of_the_allowed_family_and_none_of_another(self):
        self.bury("dead-fade", self.card(), reason="Refuted: the fade loses after costs.")
        self.bury("dead-condor", None, reason="Refuted: selling premium loses.", structure="iron_condor",
                  mechanism="Selling rich premium, the variance risk premium, on SPY decays into the close.")
        arch = self.arch()
        self.assertEqual(arch.cell_families(), ("directional",), "debit verticals and long singles are one structure family")
        index = cards.RebirthIndex(self.store, self.settings)
        self.assertEqual({cards.cell_of(r["key"])[1] for r in index.rows}, {"directional", "short_premium"})
        lines = index.cells(claimable=2, families=arch.cell_families())
        self.assertEqual(len(lines), 44, "11 mechanism classes x 4 holding periods")
        self.assertEqual({line.split(":")[0] for line in lines}, GRID)
        read = "+".join(index.by_id["dead-fade"]["inputs"])
        self.assertEqual(lines[0], "reversal_liquidity / directional / days_1_3: 1 rows (1 carded), rebirth room 2, newest "
                                   f"dead-fade; claimable: dead-fade (read {read}, carded)", "its room and its claimable rows")
        self.assertEqual(sum(1 for line in lines if line.endswith(": no row: a card here needs no rebirth")), 43)
        block = arch.card_block()
        self.assertIn("BIRTH CELLS (mechanism_class / structure family / holding: every cell a birth may land in now",
                      block)
        self.assertNotIn("REFUTED CELLS", block)
        self.assertNotIn("dead-condor", block, "no line for a structure type no birth may be")
        self.assertNotIn("short_premium /", block)
        for cell in GRID:
            self.assertIn(cell + ":", block)
        self.assertIn(block, arch.prompt(), "the request carries it")

    def test_every_type_allowed_keeps_the_refuted_cells_as_they_were(self):
        self.bury("dead-fade", self.card(), reason="Refuted: the fade loses after costs.")
        self.bury("dead-condor", None, reason="Refuted: selling premium loses.", structure="iron_condor",
                  mechanism="Selling rich premium, the variance risk premium, on SPY decays into the close.")
        self.settings["architect"]["structures"] = None
        arch = self.arch()
        self.assertIsNone(arch.cell_families())
        block = arch.card_block()
        self.assertIn("REFUTED CELLS (", block)
        self.assertNotIn("BIRTH CELLS", block)
        self.assertIn("volatility_risk_premium / short_premium / intraday: 1 rows", block)
        self.assertEqual(len(cards.RebirthIndex(self.store, self.settings).cells(claimable=2)), 2, "only the cells with rows")

    def test_cells_with_room_come_first_then_the_empty_ones_then_the_full_ones(self):
        self.settings["architect"]["max_rebirths_per_cell"] = 1
        self.bury("dead-fade", self.card(), reason="Refuted: the fade loses after costs.")
        self.bury("dead-trend", self.card(TREND), reason="Refuted: the continuation is priced.")
        index = cards.RebirthIndex(self.store, self.settings)
        index.note_birth({"rebirth": {"row": "dead-fade"}}, "debit_vertical")  # the cell's one rebirth of the window
        lines = index.cells(claimable=2, families=("directional",))
        self.assertTrue(lines[0].startswith("trend_momentum / directional / days_4_10: 1 rows (1 carded), rebirth room 1"))
        self.assertIn("; claimable: dead-trend", lines[0])
        self.assertTrue(all(line.endswith("needs no rebirth") for line in lines[1:43]))
        self.assertTrue(lines[43].startswith("reversal_liquidity / directional / days_1_3: 1 rows (1 carded), rebirth room 0"))
        self.assertNotIn("claimable", lines[43], "a cell with no room names no row to claim")

    def test_the_list_keeps_every_cell_inside_its_size(self):
        for c in cards.MECHANISM_CLASSES:
            for h in cards.HOLDING:
                self.bury(f"{c}-{h}".replace("_", "-")[:36], self.card({**CARD, "mechanism_class": c, "holding": h}),
                          reason="Refuted: it loses after costs.")
        index = cards.RebirthIndex(self.store, self.settings)
        whole = index.cells(claimable=2, families=("directional",))
        self.assertEqual(sum("; claimable: " in line for line in whole), 44)
        size = sum(len(line) + 1 for line in whole)
        bare = sum(len(line.split("; claimable: ")[0]) + 1 for line in whole)
        self.assertEqual(index.cells(claimable=2, families=("directional",), chars=size), whole, "it fits: nothing is cut")
        budget = (size + bare) // 2
        cut = index.cells(claimable=2, families=("directional",), chars=budget)
        self.assertEqual([line.split(":")[0] for line in cut], [line.split(":")[0] for line in whole], "every cell keeps its line")
        self.assertLessEqual(sum(len(line) + 1 for line in cut), budget)
        self.assertEqual(len(index.cells(claimable=2, families=("directional",), chars=10)), 44, "never fewer cells")
        named = ["; claimable: " in line for line in cut]
        self.assertTrue(named[0] and not named[-1], "the last cells give up their claimable rows first")
        self.assertEqual(named, sorted(named, reverse=True))
        self.assertLess(sum(len(line) + 1 for line in whole), BIRTH_CELLS_CHARS, "44 cells at two rows each are well inside it")


# ------------------------------------------------------------------------------------------ 2. no paid pass without a cell
class UnpaidPass(CardCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"].update(structures=list(ALLOWED), claimable_rows=2, max_rebirths_per_cell=0)
        self.router = Asked()

    def arch(self) -> Architect:
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def fill(self, skip=()):
        for c in cards.MECHANISM_CLASSES:
            for h in cards.HOLDING:
                if (c, h) in skip:
                    continue
                card, errors = cards.validate({**CARD, "mechanism_class": c, "holding": h})
                self.assertEqual(errors, [])
                self.bury(f"{c}-{h}".replace("_", "-")[:36], card, reason="Refuted: it loses after costs.")

    def events(self):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.architect"]

    def test_a_pass_no_cell_could_bear_in_asks_no_model_and_is_recorded(self):
        last = ("dispersion", "intraday")
        self.fill(skip=(last,))
        self.assertIsNone(self.arch().closed(), "one cell holds no row: a card there needs no rebirth")
        card, _ = cards.validate({**CARD, "mechanism_class": last[0], "holding": last[1]})
        self.bury("dispersion-intraday", card, reason="Refuted: it loses after costs.")
        arch = self.arch()
        self.assertEqual(arch.closed(), {"cells": 44, "full": 44, "spent": 0})
        self.clock.advance(100)
        out = arch.run()
        self.assertEqual(self.router.calls, [], "no model was asked")
        self.assertEqual((out["born"], out["skipped"]), ([], SKIPPED_NO_CELL))
        self.assertIn("no cell a birth may land in has rebirth room or is open", out["why"])
        self.assertEqual(out["cells"], {"cells": 44, "full": 44, "spent": 0})
        self.assertNotIn("cost_usd", out)
        self.assertEqual(self.events(), [out], "one event the funnel can count")
        self.assertEqual(self.store.get("architect_at"), self.clock(), "the pass counts as made: the next is at its cadence")
        self.assertEqual(self.store.spent(), 0.0, "nothing was billed")

    def test_room_in_one_cell_and_the_model_is_asked(self):
        self.fill()
        self.settings["architect"]["max_rebirths_per_cell"] = 1
        arch = self.arch()
        self.assertIsNone(arch.closed())
        out = arch.run()
        self.assertEqual(len(self.router.calls), 1)
        self.assertNotIn("skipped", out)
        # A cell with room whose every row has backed its rebirths bears nothing either.
        self.settings["architect"]["max_rebirths_per_row"] = 0
        self.assertEqual(self.arch().closed(), {"cells": 44, "full": 0, "spent": 44})

    def test_only_a_restricted_card_checked_pass_is_ever_skipped(self):
        self.fill()
        self.assertIsNotNone(self.arch().closed())
        for key, value in (("structures", None), ("require_card", False), ("card_rebirth", "off")):
            settings = copy.deepcopy(self.settings)
            settings["architect"][key] = value
            self.assertIsNone(Architect(self.store, self.router, settings, clock=self.clock).closed(), key)
        with mock.patch.object(cards.RebirthIndex, "grid", side_effect=RuntimeError("unreadable")):
            self.assertIsNone(self.arch().closed(), "a reading that fails never skips a pass")

    def test_the_whole_round_is_skipped_before_the_strategist(self):
        self.fill()
        seen: list[str] = []
        strategist = SimpleNamespace(due=lambda: True, run=lambda **kw: seen.append("strategist") or {})
        out = Swarm.architect_pass(SimpleNamespace(architect=self.arch(), strategist=strategist, clock=self.clock))
        self.assertEqual((out["skipped"], seen, self.router.calls), (SKIPPED_NO_CELL, [], []))
        self.assertEqual(len(self.events()), 1)

    def test_the_ceiling_is_a_skipped_pass_too(self):
        self.settings["population"]["ceiling"] = 0
        out = self.arch().run()
        self.assertEqual((out["skipped"], out["why"], self.router.calls), (SKIPPED_CEILING, "the population is at its ceiling", []))


# ------------------------------------------------------------------------------------------------ 3. settings as code
class Policy(unittest.TestCase):
    #: Each key F1 adds or moves: (block, key, the House's value in policy.json, the default in settings.py).
    KEYS = (("architect", "max_rebirths_per_cell", 12, 3), ("tournament", "retire_revisions", 100, 30),
            ("population", "floor_researching", True, True), ("researcher", "parked_dormancy", True, True),
            ("researcher", "retire_hold_untested", True, True), ("researcher", "retire_short_checks", 5, 5),
            ("researcher", "retire_short_cycles", 10, 10), ("strategist", "gym_roots_only", True, True),
            ("tournament", "reuse_validations", True, True))

    def test_the_committed_policy_and_the_defaults_carry_every_key(self):
        policy = json.loads(REAL_POLICY_PATH.read_text())
        for block, key, house, default in self.KEYS:
            self.assertEqual(policy[block][key], house, f"policy.json {block}.{key}")
            self.assertEqual(S.DEFAULTS[block][key], default, f"settings.DEFAULTS {block}.{key}")
        self.assertEqual(S.policy_shape(policy), [])
        self.assertNotIn("cell_yield", policy["architect"], "F1 does not switch the cell's yield on")
        self.assertNotIn("hold_until_news", policy["researcher"], "holds stay parked until news (the default)")
        self.assertIs(S.DEFAULTS["researcher"]["hold_until_news"], True)
        loaded = S.load(None, config={}, policy=policy)
        self.assertEqual((loaded["architect"]["max_rebirths_per_cell"], loaded["tournament"]["retire_revisions"]), (12, 100))


# ------------------------------------------------------------------------------------------------ 4. parked dormancy
class ParkedDormancy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["researcher"]["dormant_cycles"] = 4
        self.settings["population"].update(start=1, floor=1)
        self.fid = self.store.add_family(family_spec(SEEDS[0]), origin="seed")["id"]
        self.scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)

    def park(self, fid=None):
        fid = fid or self.fid
        self.assertEqual(self.scheduler.take(idle_seconds=0), fid)
        self.store.set_state(fid, dormant_cycles=1)
        self.scheduler.release(fid, {"hold": True, "dormant_cycles": 1})

    def count(self, seconds):
        self.clock.advance(seconds)
        return self.scheduler.count_parked()

    def dormant(self):
        return dormant_count(self.store.family(self.fid))

    def test_a_park_counts_a_dormant_cycle_each_hold_wait_and_buys_no_turn(self):
        self.assertIs(self.settings["researcher"]["hold_until_news"], True)
        self.park()
        self.assertEqual(self.count(PARKED_EVERY), [], "parked for half a minute")
        self.assertEqual(self.count(300 - 2 * PARKED_EVERY), [], "one second short of the hold wait")
        self.assertEqual(self.count(PARKED_EVERY), [self.fid])
        self.assertEqual(self.dormant(), 2)
        self.assertEqual(self.count(PARKED_EVERY), [], "counted: the next is a hold wait later")
        self.assertEqual(self.count(300), [self.fid])
        self.assertEqual(self.dormant(), 3)
        self.assertIsNone(self.scheduler.take(idle_seconds=0), "still parked: a count is never a paid turn")
        self.assertEqual(self.scheduler.waiting(), 1)

    def test_a_stopped_swarms_hours_count_once_and_the_count_stops_at_the_clause(self):
        self.park()
        self.assertEqual(self.count(10 * 3600), [self.fid], "ten hours parked while nothing ran: one cycle, not 120")
        self.assertEqual(self.dormant(), 2)
        self.scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)  # a restart keeps the count's clock
        self.assertEqual(self.count(PARKED_EVERY), [])
        for expected in (3, 4):
            self.assertEqual(self.count(300), [self.fid])
            self.assertEqual(self.dormant(), expected)
        self.assertEqual(self.count(300), [], "at researcher.dormant_cycles the idle rule decides: no further count")
        self.assertEqual(self.dormant(), 4)
        self.assertIn("made no new Gym evaluation in its last 4 cycles", idle_dead(self.store.family(self.fid), self.settings))

    def test_news_a_cycle_the_timer_and_the_switch_stop_the_count(self):
        self.park()
        self.store.note(self.fid, "The operator: test the same exposure without the signal.")
        self.assertEqual(self.count(600), [], "news lifted the park: a family owed a turn is never counted as waiting")
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.assertEqual(self.count(600), [], "in a cycle")
        self.store.set_state(self.fid, dormant_cycles=1)
        self.scheduler.release(self.fid, {"hold": True, "dormant_cycles": 1})
        for key, value in (("parked_dormancy", False), ("hold_until_news", False), ("dormant_cycles", 0)):
            settings = copy.deepcopy(self.settings)
            settings["researcher"][key] = value
            self.clock.advance(600)
            self.assertEqual(Scheduler(self.store, clock=self.clock, settings=settings).count_parked(), [], key)
        self.assertEqual(self.dormant(), 1)
        self.store.set_band(self.fid, "candidate", reason="synthetic")
        self.assertEqual(self.count(600), [], "the Gym band only")

    def test_a_parked_dead_slot_leaves_by_itself(self):
        """The standstill, small: the only family is parked at a floor of one. Its park counts to the clause, the idle
        pass retires it, and no model was asked."""
        self.park()
        pool = FakeGymPool(lambda job: result(job.name))
        tournament = Tournament(self.store, pool, self.settings, clock=self.clock)
        self.assertEqual(tournament.idle_pass()["retired"], [])
        for _ in range(3):
            self.count(300)
        self.assertEqual(self.dormant(), 4)
        [row] = tournament.idle_pass()["retired"]
        self.assertEqual(row["family"], self.fid)
        self.assertIn("made no new Gym evaluation in its last 4 cycles", row["why"])
        self.assertEqual(self.store.families(alive=True), [])
        self.assertEqual(self.store.spent(), 0.0)


class ParkedCountInTheLoop(LoopCase):
    def test_the_main_loop_counts_only_while_a_cycle_could_run(self):
        """As the timer's holds did: never under the guard's brake and never over the researchers' pace."""
        sw = self.swarm()
        for key in ("tournament_at", "architect_at"):
            self.store.put(key, time.time())  # no round is due: this is about the count alone
        calls: list[int] = []
        sw.scheduler.count_parked = lambda: calls.append(1) or []
        sw.step()
        self.assertEqual(len(calls), 1)
        self.guard.braked = True
        sw.step()
        self.assertEqual(len(calls), 1, "under the brake nothing researches, and nothing is counted as waiting")
        self.guard.braked = False
        self.store.add_spend("sail_model", 500.0, family="a-family", detail={"key": "swarm:a-family:c1:m0:0"})
        sw._pace = (float("-inf"), "", 0.0)
        self.assertTrue(sw.over_pace())
        sw.step()
        self.assertEqual(len(calls), 1, "over the pace no cycle could have run")


# ------------------------------------------------------------------------------------------ 5. the floor counts research
class Turnover(RoundCase):
    """Oct 3 in small: eight living families, all parked, at a floor of eight."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=12, ceiling=12, floor=8)
        self.settings["researcher"]["dormant_cycles"] = 3
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        self.scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)
        self.ids = [self.slot(f"slot-{i}") for i in range(8)]

    def slot(self, fid):
        """A family with no best to validate (as the eight of Oct 3 were: 3 to 9 trials, no eligible Train version)."""
        self.family(fid)
        self.store.update_family(fid, best_version=None)
        return fid

    def park_all(self):
        while True:
            fid = self.scheduler.take(idle_seconds=0)
            if fid is None:
                return
            self.store.set_state(fid, dormant_cycles=1, hold_streak=1)
            self.scheduler.release(fid, {"hold": True, "dormant_cycles": 1})

    def tournament(self):
        return Tournament(self.store, self.pool, self.settings, clock=self.clock)

    def test_eight_parked_families_at_the_floor_turn_over(self):
        self.park_all()
        self.assertEqual(self.scheduler.waiting(), 8)
        self.assertEqual(self.tournament().idle_pass()["retired"], [], "parked a moment ago: none is dead")
        self.assertEqual(Architect(self.store, None, self.settings, clock=self.clock).want(), 4,
                         "births are never held by the floor: the architect bears up to the start and the ceiling")
        for _ in range(2):
            self.clock.advance(300)
            self.assertEqual(len(self.scheduler.count_parked()), 8)
        counts = floor_counts(self.settings)
        self.assertEqual([counts(f) for f in self.store.families(alive=True)], [False] * 8, "eight dead slots, none counted")
        out = self.tournament().idle_pass()
        self.assertEqual(sorted(r["family"] for r in out["retired"]), sorted(self.ids))
        self.assertEqual(out["alive"], 0, "the floor holds no dead family for its own sake")

    def test_the_floor_still_holds_every_family_that_researches(self):
        self.park_all()
        for _ in range(2):
            self.clock.advance(300)
            self.scheduler.count_parked()
        living = [self.slot(f"living-{i}") for i in range(3)]
        counts = floor_counts(self.settings)
        self.assertEqual(sum(1 for f in self.store.families(alive=True) if counts(f)), 3)
        refused = self.store.retire_gym(living[0], "Costs defeated the mechanism.", floor=8, source="researcher", counts=counts)
        self.assertEqual((refused["status"], refused["deferred"]), ("refused", "population_floor"),
                         "three research, the floor is eight: none of the three may leave")
        self.assertEqual(self.store.retire_gym(self.ids[0], "Dead.", floor=8, source="tournament", counts=counts)["status"],
                         "retired", "a dead slot leaves whatever the count")
        self.assertEqual(sorted(r["family"] for r in self.tournament().idle_pass()["retired"]), sorted(self.ids[1:]))
        self.assertEqual(sorted(f["id"] for f in self.store.families(alive=True)), sorted(living))
        # Above the floor a researching family retires as ever.
        self.assertEqual(self.store.retire_gym(living[0], "Costs.", floor=2, source="researcher", counts=counts)["status"],
                         "retired")
        self.assertEqual(self.store.retire_gym(living[1], "Costs.", floor=2, source="researcher", counts=counts)["status"],
                         "refused")

    def test_what_a_dead_slot_is(self):
        fam = self.store.family(self.ids[0])
        self.assertFalse(dead_slot(fam, self.settings), "a family that researches")
        self.store.set_state(fam["id"], hold_streak=3)
        self.assertTrue(dead_slot(self.store.family(fam["id"]), self.settings), "three holds in a row, nothing pending")
        for pending in ({"gate_ready": True}, {"look_inflight": {"sha": "x"}}, {"best_train_version": 1},
                        {"validation_version": 1, "extension_hold": {"version": 1, "checks": "6/8", "at": "x"}}):
            self.store.set_state(fam["id"], **pending)
            self.assertFalse(dead_slot(self.store.family(fam["id"]), self.settings), pending)
            self.store.set_state(fam["id"], **{k: None for k in pending})
        self.assertTrue(dead_slot(self.store.family(fam["id"]), self.settings))
        self.store.set_state(fam["id"], hold_streak=2)
        self.assertFalse(dead_slot(self.store.family(fam["id"]), self.settings), "two holds")
        self.store.set_state(fam["id"], dormant_cycles=3)
        self.assertTrue(dead_slot(self.store.family(fam["id"]), self.settings), "dead by the idle rule")
        self.store.set_band(fam["id"], "candidate", reason="synthetic")
        self.assertFalse(dead_slot(self.store.family(fam["id"]), self.settings), "another band is never one")
        self.settings["population"]["floor_researching"] = False
        self.assertIsNone(floor_counts(self.settings), "the switch: every living family counts, as before")

    def test_a_family_the_cohort_keep_holds_always_counts(self):
        fid = self.ids[0]
        self.store.set_state(fid, hold_streak=5)
        fam = self.store.family(fid)
        self.assertFalse(floor_counts(self.settings)(fam), "a dead slot")
        self.assertTrue(floor_counts(self.settings, kept=lambda f: f == fid)(fam), "practising for the ladder: counted")
        tournament = self.tournament()
        self.assertFalse(tournament.floor_counts()(fam))
        self.store.put(KEEP_KV, {"at": self.clock(), "families": {fid: 1}})  # the tournament's saved keep
        self.assertTrue(tournament.floor_counts()(fam))
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, contract="")
        self.assertTrue(researcher.floor_counts()(fam))
        self.assertFalse(researcher.floor_room(fam), "one counted family at a floor of eight: it may not leave")
        self.clock.advance(KEEP_KV_SECONDS + 1)
        self.assertFalse(researcher.floor_counts()(fam), "a keep too old to trust says nothing")
        self.assertTrue(researcher.floor_room(fam))


# ------------------------------------------------------------------------------------------------ 6. the pace
class ArchitectOutOfThePace(LoopCase):
    def test_one_architect_pass_does_not_pause_the_researchers(self):
        self.settings["researcher"].update(usd_per_hour=4.0, sail_usd_per_hour=0.05)
        self.store.add_spend("sail_model", 0.0873, family="swarm",
                             detail={"desk": "swarm", "key": "swarm:architect:1791030654", "profile": "pro_asap"})
        self.store.add_spend("sail_model", 0.0412, family="swarm",
                             detail={"desk": "swarm", "key": "swarm:architect:1791030654:salvage", "profile": "pro_asap"})
        sw = self.swarm()
        clock = [time.time()]
        sw.clock = lambda: clock[0]
        self.assertFalse(sw.over_pace(), "the architect's own pass is not the researchers' stream")
        pace = sw.status()["researcher_pace"]
        self.assertEqual((pace["scope"], pace["spent_last_hour_usd"], pace["paused"]), ("sail_model", 0.0, False))
        self.assertAlmostEqual(self.store.spent(["sail_model"]), 0.1285, msg="every dollar of it is still in the day's Sail spend")
        self.assertAlmostEqual(architect_spent(self.store, ["sail_model"], clock[0] - 3600), 0.1285)
        self.store.add_spend("sail_model", 0.03, family="a-family",
                             detail={"desk": "a-family", "key": "swarm:a-family:c3:m0:2", "profile": "flash_asap"})
        clock[0] += 11
        self.assertFalse(sw.over_pace())
        self.assertEqual(sw.status()["researcher_pace"]["spent_last_hour_usd"], 0.03)
        self.store.add_spend("sail_model", 0.03, family="a-family",
                             detail={"desk": "a-family", "key": "swarm:a-family:c4:m0:2", "profile": "flash_asap"})
        clock[0] += 11
        self.assertTrue(sw.over_pace(), "the researchers' own spend still stops them at the pace")
        self.assertIn("Sail models spent $0.0600", sw.status()["researcher_pace"]["reason"])

    def test_the_combined_pace_leaves_out_the_architect_on_either_meter(self):
        self.settings["researcher"].update(usd_per_hour=1.0, sail_usd_per_hour=None)
        self.store.add_spend("openai", 2.0, detail={"role": "architect", "hold": "swarm:architect:1791030700"})
        self.store.add_spend("sail_model", 0.4, family="a-family", detail={"key": "swarm:a-family:c1:m0:0"})
        sw = self.swarm()
        self.assertFalse(sw.over_pace())
        pace = sw.status()["researcher_pace"]
        self.assertEqual((pace["scope"], pace["spent_last_hour_usd"]), ("all_models", 0.4))
        self.assertEqual(self.store.spent(["openai"]), 2.0)


# ------------------------------------------------------------------------------------------------ 7. the Gym's roots
ROOTS = ["SPY", "QQQ", "IWM", "XSP", "SPXW", "AMD", "NVDA", "MU", "SMH", "TLT", "GLD"]
FOREIGN = "(e) Rate-sensitive funds: when XLU and LQD fall together, TLT follows within a session; fade it with debit verticals."


class GymRoots(unittest.TestCase):
    def test_what_reads_as_a_root_the_gym_does_not_hold(self):
        cases = {
            "sector funds XLU, XLV and XLY ahead of SPY": ["XLU", "XLV", "XLY"],
            "use $LQD stress as the signal for IWM": ["LQD"],
            "when VIX is high buy SPY calls": ["VIX"],
            "pairs of AMD, NVDA, INTC and MU": ["INTC"],
            "SPX is not held; SPXW is": ["SPX"],
            "SMH/QQQ vs SOXX": ["SOXX"],
            "STOP proposing TLT AND GLD drift carriers; READ the DRIFT, STRESS and THIN rows": [],
            "ONE direction: SMH, QQQ at 1-7 DTE; the IV and OTM choices on SPY": [],
            "ETF, DTE and IV are words": [],
            CLEAN: [],
        }
        for text, named in cases.items():
            self.assertEqual(foreign_roots(text, ROOTS), named, text)
        self.assertEqual(foreign_roots("funds XLU and LQD", ROOTS + ["XLU", "LQD"]), [], "an admitted root is never foreign")

    def test_the_validator_refuses_the_section_and_names_the_tickers(self):
        known = frozenset(CITES)
        ok = check_section(CLEAN, max_chars=1600, cites=CITES, known_ids=known, min_cites=3, roots=ROOTS)
        self.assertEqual((ok.ok, ok.reasons), (True, []))
        bad = check_section(CLEAN + "\n" + FOREIGN, max_chars=1600, cites=CITES, known_ids=known, min_cites=3, roots=ROOTS)
        self.assertFalse(bad.ok)
        self.assertEqual(bad.reasons, ["roots: XLU, LQD: not among the Gym's roots, which are the only tickers a program can "
                                       "read or trade (THE GYM'S ROOTS)"])
        off = check_section(CLEAN + "\n" + FOREIGN, max_chars=1600, cites=CITES, known_ids=known, min_cites=3)
        self.assertTrue(off.ok, "no roots given: the rule is off, as before")
        # A cited id is a name: its parts never read as a ticker.
        ids = frozenset({*CITES, "xlu-lead-smh"})
        cited = check_section(CLEAN + "\n(e) Do not re-propose xlu-lead-smh.", max_chars=1600, cites=CITES, known_ids=ids,
                              min_cites=3, roots=ROOTS)
        self.assertTrue(cited.ok, cited.reasons)


class GymRootsRuns(StrategistCase):
    def setUp(self):
        super().setUp()
        self.settings["gym"]["roots"] = list(ROOTS)

    def test_a_section_naming_a_root_the_gym_lacks_is_refused_and_repaired(self):
        router = FakeRouter([reply(CLEAN + "\n" + FOREIGN), reply()], clock=self.clock, seconds=100)
        out = self.strategist(router).run()
        self.assertEqual((out["accepted"], out["turns"]), (True, 2))
        self.assertEqual(out["attempts"][0]["reasons"], ["roots: XLU, LQD: not among the Gym's roots, which are the only tickers "
                                                         "a program can read or trade (THE GYM'S ROOTS)"])
        first, second = router.calls
        self.assertIn("THE GYM'S ROOTS (the only tickers a program can read or trade, as a signal or as the traded root; name "
                      "no other): " + ", ".join(ROOTS) + ".", first["claude_user"])
        self.assertIn("names a ticker that is not one of the Gym's roots", first["claude_system"])
        self.assertIn("roots: XLU, LQD: not among the Gym's roots", second["claude_user"])
        self.assertEqual(self.store.get(AGENDA_KEY)["text"], CLEAN)

    def test_a_final_refusal_keeps_the_last_section_and_the_switch_turns_the_rule_off(self):
        self.settings["strategist"]["repair_turns"] = 0
        out = self.strategist(FakeRouter(reply(CLEAN + "\n" + FOREIGN))).run()
        self.assertFalse(out["accepted"])
        self.assertIsNone(self.store.get(AGENDA_KEY), "nothing was accepted")
        self.clock.advance(4 * 3600)
        self.settings["strategist"]["gym_roots_only"] = False
        out = self.strategist(FakeRouter(reply(CLEAN + "\n" + FOREIGN))).run()
        self.assertTrue(out["accepted"], out.get("reasons"))

    def test_a_section_accepted_before_the_rule_is_named_to_both_readers(self):
        stale = CLEAN + "\n" + FOREIGN
        self.store.put(AGENDA_KEY, {"text": stale, "at": "2026-10-02T16:54:19Z", "run": 1})
        architect = Architect(self.store, None, self.settings, clock=self.clock)
        _, agenda = architect.agenda()
        note = FOREIGN_ROOTS_NOTE.format(names="XLU, LQD")
        self.assertTrue(agenda.endswith(note), "the harness's own line, after the quoted section")
        self.assertIn("which the Gym does not hold", note)
        self.assertFalse(note.strip().startswith(">"), "outside the quote")
        packet = self.strategist(FakeRouter(reply())).packet()
        self.assertIn("The current section names XLU, LQD, which the Gym does not hold: do not carry them over.", packet)
        self.store.put(AGENDA_KEY, {"text": CLEAN, "at": "2026-10-02T16:54:19Z", "run": 1})
        self.assertNotIn("The harness, not the strategist", architect.agenda()[1], "a section that names none: as before")


# ------------------------------------------------------------------------------------------------ 8. the depth rule
def line(met: int, total: int = 8, passed: bool = False) -> dict:
    names = ("status_ok", "trades", "days", "mean_positive", "t", "dsr", "quarters", "stress")[:total]
    return {"passed": passed, "checks": {name: i < met for i, name in enumerate(names)}}


class DepthRule(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)

    def validated(self, fid="a", met=5, cycles_then=20, cycles_now=29, **state):
        self.family(fid)
        self.store.update_family(fid, cycles=cycles_now, validated_version=1, validations=1)
        self.store.set_state(fid, validation_line=line(met), validation_version=1, **{VALIDATED_CYCLES_KEY: cycles_then}, **state)
        return self.store.family(fid)

    def test_five_checks_or_fewer_and_ten_cycles_later_the_family_is_dead(self):
        self.assertEqual((self.settings["researcher"]["retire_short_checks"], self.settings["researcher"]["retire_short_cycles"]),
                         (5, 10))
        fam = self.validated(met=5, cycles_then=20, cycles_now=29)
        self.assertIsNone(idle_dead(fam, self.settings), "nine cycles after it")
        self.assertEqual(short_left(fam, self.settings), 1)
        self.store.bump("a", cycles=1)
        fam = self.store.family("a")
        self.assertEqual(idle_dead(fam, self.settings),
                         "kept researching for 10 cycles after a validation that met 5 of the line's 8 checks")
        self.assertEqual(short_left(fam, self.settings), 0)
        self.assertTrue(dead_slot(fam, self.settings))

    def test_six_checks_or_more_keeps_researching_whatever_the_cycles(self):
        for met in (6, 7):
            fam = self.validated(f"near-{met}", met=met, cycles_then=0, cycles_now=500)
            self.assertIsNone(short_dead(fam, self.settings), met)
            self.assertIsNone(short_left(fam, self.settings))
        fam = self.validated("passed", met=8, cycles_then=0, cycles_now=500)
        self.store.set_state("passed", validation_line=line(8, passed=True))
        self.assertIsNone(idle_dead(self.store.family("passed"), self.settings))

    def test_what_never_counts(self):
        never = self.family("never")
        self.store.update_family("never", cycles=500)
        self.assertIsNone(short_dead(self.store.family("never"), self.settings), "never validated")
        self.assertIsNone(never["state"].get(VALIDATED_CYCLES_KEY))
        fam = self.validated("unmarked", met=2, cycles_then=0, cycles_now=500)
        self.store.set_state("unmarked", **{VALIDATED_CYCLES_KEY: None})
        self.assertIsNone(short_dead(self.store.family("unmarked"), self.settings), "validated before the mark was kept")
        fam = self.validated("gated", met=2, cycles_then=0, cycles_now=500, gate_ready=True)
        self.assertIsNotNone(short_dead(fam, self.settings))
        self.assertIsNone(idle_dead(fam, self.settings), "the idle rule's own exemptions stand: never at the gate")
        fam = self.validated("off", met=2, cycles_then=0, cycles_now=500)
        for key in ("retire_short_checks", "retire_short_cycles"):
            for value in (0, None, True, "many"):
                settings = copy.deepcopy(self.settings)
                settings["researcher"][key] = value
                self.assertIsNone(idle_dead(fam, settings), (key, value))
        self.store.set_band("off", "candidate", reason="synthetic")
        self.assertIsNone(short_dead(self.store.family("off"), self.settings), "the Gym band only")

    def test_the_tournament_marks_the_validation_and_the_idle_pass_retires_ten_cycles_later(self):
        self.answer = weak
        self.family("a")
        self.store.update_family("a", cycles=7, best_train=0.4)
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        met, total = checks_met(fam["state"]["validation_line"])
        self.assertEqual((total, fam["state"][VALIDATED_CYCLES_KEY]), (8, 7), "the family's cycles when it was judged")
        self.assertLessEqual(met, 5)
        self.store.bump("a", cycles=9)
        self.assertEqual(t.idle_pass()["retired"], [])
        self.store.bump("a", cycles=1)
        [row] = t.idle_pass()["retired"]
        self.assertEqual(row["why"], f"It kept researching for 10 cycles after a validation that met {met} of the line's 8 "
                                     f"checks. {idle_cause('short')}")
        gone = self.store.family("a")
        self.assertEqual(tag_of({"family": "a", "lesson": ""}, gone), "EXHAUSTED", "a tested finding, never a refuting row")
        self.assertNotIn("EXHAUSTED", cards.MECHANISM_VERDICTS)
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(event["cause"], "Retired by the idle rule after its Train record was screened.",
                         "the public cause carries no count and no figure")

    def test_a_later_validation_restarts_the_count_and_a_rejudged_one_does_not(self):
        self.answer = weak
        self.family("a")
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        t.validate(self.store.families(alive=True))
        self.store.bump("a", cycles=6)
        v2 = self.store.add_version("a", "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return [None]\n", {},
                                    author="model")
        self.store.update_family("a", best_version=v2["n"])
        t.validate(self.store.families(alive=True))
        self.assertEqual(self.store.family("a")["state"][VALIDATED_CYCLES_KEY], 6, "a counted validation: from here")
        self.store.bump("a", cycles=6)
        self.store.update_family("a", best_version=1)  # the first version submitted again: judged from its record
        jobs = len(self.pool.jobs)
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        self.assertEqual((len(self.pool.jobs), fam["state"]["validation_version"], fam["state"][VALIDATED_CYCLES_KEY]), (jobs, 1, 6))
        self.assertIsNone(idle_dead(fam, self.settings), "six cycles since the last counted validation")
        self.store.bump("a", cycles=4)
        self.assertIsNotNone(idle_dead(self.store.family("a"), self.settings))


class DepthStatus(ResearcherCase):
    def test_the_researcher_reads_its_countdown(self):
        fid = self.fam["id"]
        self.store.update_family(fid, cycles=23, validated_version=1, validations=1)
        self.store.set_state(fid, validation_line=line(3), validation_version=1, **{VALIDATED_CYCLES_KEY: 20})
        status = self.researcher().status(self.store.family(fid))
        self.assertIn("Validation of version 1: it did not meet the validation line (3 of 8 checks passed).", status)
        self.assertIn("so the idle rule retires your family 7 cycles from now, whatever awaits validation then", status)
        self.store.set_state(fid, validation_line=line(6))
        self.assertNotIn("the idle rule retires your family", self.researcher().status(self.store.family(fid)))


# ------------------------------------------------------------------------ 8. an identical program is validated once
PROGRAM = "NEEDS = {'roots': ['SPY']}\nPARAMS = {'width': 2}\ndef decide(ctx):\n    return []\n"
ROOTLESS = "PARAMS = {'width': 2}\ndef decide(ctx):\n    return []\n"


class ValidatedOnce(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)
        self.image = "sbcp_gym_one"
        self.pool.image = lambda kind="gym": self.image
        self.pool.bundle = lambda: "bundle-one"
        self.verdict = strong
        self.answer = lambda job: {**self.verdict(job), "gym_image": self.image, "gym_bundle": "bundle-one"}

    def born(self, fid, *, parent=None, code=PROGRAM, params=None, roots=("SPY",), origin="seed"):
        fam = self.store.add_family({**SPEC, "id": fid, "roots": list(roots)}, origin=origin, parent=parent)
        v = self.store.add_version(fam["id"], code, params or {}, author="operator-revive" if parent else "seed")
        self.store.update_family(fam["id"], best_version=v["n"])
        return fam["id"]

    def round(self):
        return Tournament(self.store, self.pool, self.settings, clock=self.clock).validate(self.store.families(alive=True))

    def test_a_revival_that_carries_its_parents_program_inherits_the_verdict(self):
        self.born("a")
        first = self.round()
        self.assertEqual((first["queued"], len(self.pool.jobs)), (1, 1))
        self.assertNotIn("inherited", first)
        parent = self.store.family("a")
        self.born("a-r", parent="a", origin="operator-revive")
        self.store.update_family("a-r", cycles=4)
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs)), (0, 1), "the same program on the same Gym: no second job")
        [run] = self.store.runs("a", window="validation")[-1:]
        source = out["inherited"]["a-r"]
        self.assertEqual((source["family"], source["version"]), ("a", 1))
        child = self.store.family("a-r")
        self.assertEqual(child["state"]["validation_inherited"], source)
        self.assertEqual(out["judged"]["a-r"]["inherited"], source)
        self.assertEqual(child["state"]["validation_line"]["checks"], parent["state"]["validation_line"]["checks"],
                         "the same result, judged by the same line")
        self.assertEqual((child["validated_version"], child["validations"], child["trials"]), (1, 1, 0),
                         "its validation, with no trial of its own")
        self.assertEqual((child["state"]["validated_trials"], child["state"][VALIDATED_CYCLES_KEY]), (0, 4),
                         "its idle clocks run from the verdict")
        rows = self.store.runs("a-r", window="validation")
        self.assertEqual([(r["trials"], r["stress"], r["summary"]["inherited"]) for r in rows], [(0, 1.5, source), (0, 1.0, source)],
                         "its own copy of the record and of its stress twin, with no trial: nothing was evaluated")
        self.assertEqual(self.store.lineage_validated("a-r")[0], 1, "one program validated in the lineage, not two")
        self.assertEqual(self.store.lineage_trials("a-r"), self.store.lineage_trials("a"))
        self.store.update_family("a-r", validated_version=None)  # submitted again: judged from its own record
        again = self.round()
        self.assertEqual((again["queued"], len(self.pool.jobs)), (0, 1))
        self.assertEqual(self.store.family("a-r")["state"]["validation_inherited"], source, "re-judged: still inherited")
        self.assertEqual(self.store.family("a-r")["validations"], 1, "a re-judged record is no new validation")
        self.assertEqual(self.round()["queued"], 0, "validated: nothing is owed next round")
        self.assertIsNone(parent["state"].get("validation_inherited"))

    def test_another_program_another_root_or_another_gym_is_validated_itself(self):
        self.born("a")
        self.round()
        self.born("b", parent="a", params={"width": 3})
        self.assertEqual(self.round()["queued"], 1, "other params: another program")
        self.born("c", code=ROOTLESS, roots=("SPY",))
        self.assertEqual(self.round()["queued"], 1)
        self.born("d", code=ROOTLESS, roots=("QQQ",))
        self.assertEqual(self.round()["queued"], 1, "the same code on another root: another evaluation")
        self.born("e", code=ROOTLESS, roots=("SPY",))
        out = self.round()
        self.assertEqual((out["queued"], out["inherited"]["e"]["family"]), (0, "c"), "the same code on the same roots")
        self.image = "sbcp_gym_two"
        self.born("f", parent="a")
        out = self.round()
        self.assertEqual(out["queued"], 4, "a new Gym image: every program is owed again, and none is read across it")
        self.assertEqual(sorted(out["inherited"]), ["e", "f"], "each program once on the new Gym: the twins read that result")
        self.assertEqual({v["family"] for v in out["inherited"].values()}, {"a", "c"})

    def test_spelled_out_defaults_are_the_same_program(self):
        self.born("a")
        self.round()
        self.born("a-r", parent="a", params={"width": 2})
        out = self.round()
        self.assertEqual((out["queued"], out["inherited"]["a-r"]["family"]), (0, "a"), "`{}` and the default written out")

    def test_twins_in_one_round_are_validated_once(self):
        self.born("a")
        self.born("a-r", parent="a")
        out = self.round()
        self.assertEqual((out["queued"], list(out["inherited"]), out["waiting_twin"], len(self.pool.jobs)), (1, ["a-r"], [], 1),
                         "one job; the twin reads its result in the same round")
        self.assertEqual(self.store.family("a-r")["validated_version"], 1)
        # A first job that fails leaves its twin waiting, never validated on nothing.
        self.born("b", code=ROOTLESS)
        self.born("b-r", code=ROOTLESS)
        self.pool.fail.add("b")
        out = self.round()
        self.assertEqual((out["queued"], out["waiting_twin"], list(out["errors"])), (1, ["b-r"], ["b"]))
        self.assertIsNone(self.store.family("b-r")["validated_version"])
        self.pool.fail.clear()
        out = self.round()
        self.assertEqual((out["queued"], list(out["inherited"]), out["waiting_twin"]), (1, ["b-r"], []))

    def test_the_switch_validates_every_family_by_itself(self):
        self.settings["tournament"]["reuse_validations"] = False
        self.born("a")
        self.round()
        self.born("a-r", parent="a")
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs)), (1, 2))
        self.assertNotIn("inherited", out)
        self.assertIsNone(self.store.family("a-r")["state"]["validation_inherited"])

    def test_an_inherited_short_verdict_starts_the_depth_rules_count(self):
        self.verdict = weak
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        self.born("a")
        self.round()
        self.born("a-r", parent="a")
        self.round()
        child = self.store.family("a-r")
        self.assertLessEqual(checks_met(child["state"]["validation_line"])[0], 5)
        self.assertEqual(short_left(child, self.settings), 10)
        self.store.bump("a-r", cycles=10)
        self.assertIn("kept researching for 10 cycles", idle_dead(self.store.family("a-r"), self.settings))


if __name__ == "__main__":
    unittest.main()

"""F1's research stream (Oct 3, 2026): the restart made to last, each rule on the real `SwarmStore`.

Research stood still from 01:35Z Oct 3: every architect proposal was refused (the request listed cells no birth could
land in and hid the ones with room), the eight living families were parked until news and none could retire (eight was
the floor), and one architect pass paused every researcher for an hour. These tests pin what F1 changes:

- THE BIRTH CELLS: the architect's request lists every cell of the allowed structure family, and no other;
- NO PAID PASS WITHOUT A CELL: a pass no cell could bear in asks no model and is recorded as skipped;
- THE CELLS' PACE: every birth counts against its cell and the hour, so the budget cannot be spent in a few days;
- the settings as code (the cell budget, the revision limit, each new switch with its default);
- PARKED DORMANCY: a park until news counts toward the dormancy clause with `researcher.hold_until_news` left true;
- THE FLOOR COUNTS RESEARCH: dead slots leave at the floor, a researching family does not;
- A THIN RETIREMENT closes no cell; an extension hold nobody cleared ends by its age;
- the architect's own spend is out of the researchers' hourly pace;
- THE GYM'S ROOTS: a WHERE TO LOOK section that names a ticker the Gym does not hold is refused, and a stored one is
  set aside;
- THE DEPTH RULE (worked cycles) and AN IDENTICAL PROGRAM IS VALIDATED ONCE (failures only, counted in N).

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

from league.gym.results import failed as unfinished
from league.swarm import cards
from league.swarm import settings as S
from league.swarm.architect import (AGENDA_ASIDE_KEY, AGENDA_KEY, BIRTH_CELLS_CHARS, COMPOSED_AGENDA_TITLE, LOCKED_AGENDA_TITLE,
                                    SKIPPED_CEILING, SKIPPED_NO_CELL, SKIPPED_PACED, Architect, tag_of)
from league.swarm.loop import PARKED_EVERY, Scheduler, Swarm, architect_spent
from league.swarm.practice import KEEP_KV, KEEP_KV_SECONDS
from league.swarm.researcher import (THIN_RETIRED, UNIT_WAIT_KEY, VALIDATED_CYCLES_KEY, WORKED_CYCLES_KEY, Researcher, checks_met,
                                     dead_slot, dormant_count, extension_held, floor_counts, idle_cause, idle_dead,
                                     lapse_extension, park_minutes, short_dead, short_left, thin_cause, thin_evidence,
                                     worked_cycles)
from league.swarm.seeds import SEEDS, family_spec
from league.swarm.store import SwarmStore
from league.swarm.strategist import check_section, foreign_roots
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.swarm_fakes import Clock, result
from league.tests.test_swarm_cards import CARD, GOOD, MECH, proposal
from league.tests.test_swarm_cards import Case as CardCase
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import FakeGymPool, RoundCase, strong, stronger, weak
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
        unread = ", ".join(name for name in cards.INPUTS if name not in index.by_id["dead-fade"]["inputs"])
        self.assertEqual(lines[0], "reversal_liquidity / directional / days_1_3: 1 rows (1 carded), rebirth room 2, newest "
                                   f"dead-fade; a card that reads only {unread} needs no rebirth; claimable: dead-fade (read "
                                   f"{read}, carded)", "its room, the inputs its carded rows leave unread and its claimable rows")
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

    def test_a_claimed_proposal_in_a_cell_the_old_request_hid_is_born(self):
        """R6. On Oct 3 thirteen of the fifteen refusals were claimless proposals in cells the 40-line list never
        showed. The new list shows the cell with the row a claim may name, and a proposal that names it is born."""
        self.settings["architect"]["max_rebirths_per_cell"] = 12
        other = [(c, h) for c in cards.MECHANISM_CLASSES for h in cards.HOLDING][:41]
        for i, (c, h) in enumerate(other):  # 41 refuted cells of a type no birth may be, each larger than the directional one
            for k in range(2):
                self.bury(f"condor-{i}-{k}", self.card({**CARD, "mechanism_class": c, "holding": h}),
                          reason="Refuted: selling premium loses.", structure="iron_condor")
        dead = self.bury("rebound-old", self.card(), reason="Refuted: the fade loses after costs.")
        index = cards.RebirthIndex(self.store, self.settings)
        old = index.cells(claimable=2)  # the list as it was: the 40 largest refuted cells of every structure type
        self.assertEqual((len(old), any("rebound-old" in line for line in old)), (40, False), "the cell was never shown")
        self.assertTrue(all(" / short_premium / " in line for line in old))
        block = self.arch().card_block()
        self.assertIn("reversal_liquidity / directional / days_1_3: 1 rows (1 carded), rebirth room 12, newest rebound-old", block)
        self.assertIn("claimable: rebound-old (read ", block)
        a = self.arch()
        self.assertEqual(a.admit([proposal("rebound-new", mechanism="Sellers overshoot late; the next session repairs the "
                                                                   "dislocation on the index ETF.")]), [],
                         "with no claim it is refused, as on Oct 3")
        self.assertEqual(a.card_refused[0]["row"], dead)
        reborn = {**CARD, "inputs": ["clock", "open_interest", "underlying_price"], "rebirth": {"row": dead, **GOOD}}
        born = a.admit([proposal("rebound-new", card=reborn, mechanism="Dealer inventory imbalance after late selling "
                                                                        "predicts which rebounds complete next session.")])
        self.assertEqual(born, ["rebound-new"], "naming the row the request listed, with an input it did not read")
        self.assertEqual(cards.RebirthIndex(self.store, self.settings).room(("reversal_liquidity", "directional", "days_1_3")), 11)


# ------------------------------------------------------------------------------------------ 2. no paid pass without a cell
class UnpaidPass(CardCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"].update(structures=list(ALLOWED), claimable_rows=2, max_rebirths_per_cell=0)
        self.router = Asked()

    def arch(self) -> Architect:
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    #: Two cards' inputs that leave none unread between them (a cell with only one carded row is open to a card
    #: reading other inputs: `test_carded_rows_leave_room_for_a_card_that_reads_other_inputs`).
    COVER = (list(cards.INPUTS)[:6], list(cards.INPUTS)[5:])

    def fill(self, skip=(), inputs=COVER):
        for c in cards.MECHANISM_CLASSES:
            for h in cards.HOLDING:
                if (c, h) in skip:
                    continue
                for letter, names in zip("ab", inputs):
                    card, errors = cards.validate({**CARD, "mechanism_class": c, "holding": h, "inputs": names})
                    self.assertEqual(errors, [])
                    self.bury(f"{letter}-{c}-{h}".replace("_", "-")[:36], card, reason="Refuted: it loses after costs.")

    def events(self):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.architect"]

    def test_a_pass_no_cell_could_bear_in_asks_no_model_and_is_recorded(self):
        last = ("dispersion", "intraday")
        self.fill(skip=(last,))
        self.assertIsNone(self.arch().closed(), "one cell holds no row: a card there needs no rebirth")
        for letter, names in zip("ab", self.COVER):
            card, _ = cards.validate({**CARD, "mechanism_class": last[0], "holding": last[1], "inputs": names})
            self.bury(f"{letter}-dispersion-intraday", card, reason="Refuted: it loses after costs.")
        arch = self.arch()
        self.assertEqual(arch.closed(), {"cells": 44, "full": 44, "paced": 0, "spent": 0})
        self.assertEqual(arch.room_seen, {"cells": 44, "bearable": 0, "rebirths_left": 0, "paced": 0})
        self.clock.advance(100)
        out = arch.run()
        self.assertEqual(self.router.calls, [], "no model was asked")
        self.assertEqual((out["born"], out["skipped"]), ([], SKIPPED_NO_CELL))
        self.assertEqual(out["why"], "no cell a birth may land in can bear one now (no rebirth room, no row a claim may still "
                                     "name, or held by the cells' pace): no model was asked")
        self.assertEqual(out["cells"], {"cells": 44, "full": 44, "paced": 0, "spent": 0})
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
        self.assertEqual(self.arch().closed(), {"cells": 44, "full": 0, "paced": 0, "spent": 44})

    def test_carded_rows_leave_room_for_a_card_that_reads_other_inputs(self):
        """A carded row matches a proposal only when their inputs overlap. With every cell at rebirth room 0 and one
        carded row in each, a claimless card that reads none of that row's inputs is born, so such a pass is never
        skipped, and the request says which inputs the cell's rows leave unread."""
        self.fill(inputs=(["clock", "underlying_price"],))  # one carded row a cell
        arch = self.arch()
        index = cards.RebirthIndex(self.store, self.settings)
        cell = ("skew", "directional", "days_4_10")
        [row] = [rows for c, rows in index.grid(("directional",)) if c == cell][0]
        self.assertEqual((index.room(cell), row["legacy"]), (0, False))
        unread = index.unread([row])
        self.assertIn("iv_skew", unread)
        self.assertFalse(set(unread) & set(row["inputs"]))
        self.assertTrue(index.bearable(cell, [row]), "no rebirth room, and still a card can be born there without a claim")
        self.assertIsNone(arch.closed(), "so the pass is not skipped")
        self.assertEqual(arch.room_seen["bearable"], 44)
        line = next(x for x in index.cells(claimable=2, families=("directional",)) if x.startswith("skew / directional / days_4_10"))
        self.assertIn(f"; a card that reads only {', '.join(unread)} needs no rebirth", line)
        fresh = {**CARD, "mechanism_class": "skew", "holding": "days_4_10", "inputs": ["iv_skew"],
                 "hypothesis": "A steep smile overstates the wings, and the skew flattens over the following sessions, "
                               "which a debit structure at the wings is paid for."}
        words = "Steep skew across strikes cheapens the body against the wings, and the smile flattens over several sessions."
        self.assertFalse(set(cards.match_inputs(cards.validate(fresh)[0], words)) & set(row["inputs"]))
        self.assertEqual(arch.admit([proposal("claimless-skew", card=fresh, mechanism=words)]), ["claimless-skew"])
        # A legacy row (no card: prose does not say what a program read) matches whatever a card reads: no such room.
        self.bury("legacy-skew", None, reason="Refuted: the skew fade loses.",
                  mechanism="The skew of the smile steepens and the wings richen over a week, then it flattens.")
        index = cards.RebirthIndex(self.store, self.settings)
        rows = [rows for c, rows in index.grid(("directional",)) if any(r["row"] == "legacy-skew" for r in rows)][0]
        self.assertEqual(index.unread(rows), [])

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
        arch = self.arch()
        self.assertTrue(arch.due(), "no pass was ever made")
        self.clock.advance(50)
        out = Swarm.architect_pass(SimpleNamespace(root=self.store.root, architect=arch, strategist=strategist, clock=self.clock))
        self.assertEqual((out["skipped"], seen, self.router.calls), (SKIPPED_NO_CELL, [], []))
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.store.get("architect_at"), self.clock(), "the skipped pass counts as made on the loop's path")
        self.assertFalse(arch.due(), "so the loop does not skip another every step: the next is at the architect's cadence")

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
            ("tournament", "reuse_validations", True, True), ("architect", "pace_births", True, False),
            ("researcher", "max_unit_train_usd", 80, 80.0), ("researcher", "extension_hold_days", 7, 7))

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

    def test_a_family_in_a_cycle_is_never_counted_whatever_its_evidence(self):
        """The guard by itself: the park's evidence is unchanged, and only the running cycle spares the count."""
        self.park()
        self.scheduler.running.add(self.fid)  # a worker holds it (its wait is not yet cleared: the cycle has just begun)
        self.assertEqual(self.count(600), [], "in a cycle")
        self.assertEqual(self.dormant(), 1)
        self.scheduler.running.discard(self.fid)
        self.assertEqual(self.count(PARKED_EVERY), [self.fid], "the same park, counted once the cycle is over")

    def test_a_park_in_another_band_is_never_counted(self):
        """The guard by itself: the family was parked AS a Candidate, so its park's evidence is current."""
        self.store.set_band(self.fid, "candidate", reason="synthetic")
        self.park()
        self.assertEqual(self.scheduler.waiting(), 1, "parked, its evidence unchanged")
        self.assertEqual(self.count(600), [], "the Gym band only: a Candidate waiting on its forward record is honest")
        self.assertEqual(self.dormant(), 1)

    def test_a_park_the_harness_owes_a_run_is_lifted_and_never_counted(self):
        """THE OPERATOR'S RUN is the harness's to make before the model is asked: while it is owed, the wait is not the
        family's (the Swarm wires `owed` to `Researcher.operator_owed`). The park is lifted, so the family's next cycle
        makes that run: it is neither retired for waiting nor left parked with the run never made."""
        self.park()
        self.scheduler.owed = lambda fam: True
        self.assertIsNone(self.scheduler.take(idle_seconds=0), "parked")
        self.assertEqual(self.count(600), [], "not counted")
        self.assertEqual(self.dormant(), 1)
        self.assertIsNone(self.store.family(self.fid)["state"].get("research_wait"), "the park is lifted")
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid, "its next cycle is given: the harness makes the run")
        self.store.set_state(self.fid, dormant_cycles=1)
        self.scheduler.release(self.fid, {"hold": True, "dormant_cycles": 1})
        self.scheduler.owed = lambda fam: False
        self.assertEqual(self.count(600), [self.fid], "nothing owed: an ordinary park, counted")
        self.scheduler.owed = lambda fam: 1 / 0  # a reading that fails counts nothing and never stops the loop
        self.assertEqual(self.count(600), [])
        self.assertEqual(self.dormant(), 2)

    def test_the_researcher_is_told_what_a_hold_costs(self):
        self.assertEqual(park_minutes(self.settings), 20, "four waits of five minutes in this test's settings")
        self.assertEqual(park_minutes(S.DEFAULTS), S.DEFAULTS["researcher"]["dormant_cycles"] * 5)
        for key, value in (("parked_dormancy", False), ("hold_until_news", False), ("dormant_cycles", 0)):
            settings = copy.deepcopy(self.settings)
            settings["researcher"][key] = value
            self.assertIsNone(park_minutes(settings), key)
        pool = FakeGymPool(lambda job: result(job.name))
        status = Researcher(self.store, None, pool, self.settings, clock=self.clock, contract="").status(self.store.family(self.fid))
        self.assertIn("call gym_run with hold=true and say why in its note. A hold parks your family until news reaches it (a "
                      "result, a verdict, guidance, new data); with nothing of yours awaiting validation, a family that only "
                      "waits is retired by the idle rule after about 20 minutes.", status)
        self.settings["researcher"]["parked_dormancy"] = False
        status = Researcher(self.store, None, pool, self.settings, clock=self.clock, contract="").status(self.store.family(self.fid))
        self.assertNotIn("A hold parks your family", status)

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

    def test_a_family_named_architect_is_a_researcher_all_the_same(self):
        """The architect's keys are "swarm:architect:<a number>"; a family whose id is "architect" has researcher keys
        "swarm:architect:c..", and its spend stays in the researchers' pace."""
        self.settings["researcher"].update(usd_per_hour=4.0, sail_usd_per_hour=0.05)
        fam = self.store.add_family({**SPEC, "id": "architect"}, origin="seed")
        self.assertEqual(fam["id"], "architect")
        self.store.add_spend("sail_model", 0.2, family="architect", detail={"desk": "architect", "key": "swarm:architect:c3:m1:0"})
        self.store.add_spend("sail_model", 0.07, family="swarm", detail={"desk": "swarm", "key": "swarm:architect:1791030654"})
        sw = self.swarm()
        now = time.time()
        self.assertAlmostEqual(architect_spent(self.store, ["sail_model"], now - 3600), 0.07)
        self.assertTrue(sw.over_pace(), "the family's own spend stops the researchers at the pace")
        self.assertEqual(sw.status()["researcher_pace"]["spent_last_hour_usd"], 0.2)

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
            "pairs of AMD, NVDA, INTC and MU": ["INTC"],
            "SMH/QQQ vs SOXX": ["SOXX"],
            # An index named for a market the Gym holds a root on is no foreign root (SPXW, XSP and SPY are S&P roots).
            "when VIX is high buy SPY calls": [],
            "Look at SPX weeklies when the VIX term structure inverts": [],
            "RUT and NDX breadth against IWM and QQQ": [],
            # Themes, places and periods written beside a root are words, not tickers.
            "NVDA and AI capex; TSLA and EV demand; NVDA, AMD and GPU supply; TLT and UST auctions": [],
            "MU, AMD and SMH in the US or EU session, Q1 and Q4": [],
            "STOP proposing TLT AND GLD drift carriers; READ the DRIFT, STRESS and THIN rows": [],
            "ONE direction: SMH, QQQ at 1-7 DTE; the IV and OTM choices on SPY": [],
            "ETF, DTE and IV are words": [],
            CLEAN: [],
        }
        for text, named in cases.items():
            self.assertEqual(foreign_roots(text, ROOTS), named, text)
        self.assertEqual(foreign_roots("funds XLU and LQD", ROOTS + ["XLU", "LQD"]), [], "an admitted root is never foreign")
        self.assertEqual(foreign_roots("SPX weeklies when VIX is high, and NDX against RUT", ["TLT", "GLD"]),
                         ["SPX", "VIX", "NDX", "RUT"], "with no root on its market an index name is foreign like any other")
        # The rule's known limit (a heuristic: the docs say so): a lone single name outside any list is not caught.
        for missed in ("NFLX against QQQ", "COIN leads MARA", "JPM earnings lead IWM"):
            self.assertEqual(foreign_roots(missed, ROOTS), [], missed)

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

    def test_a_stored_section_that_names_a_root_the_gym_lacks_is_set_aside(self):
        """R4. The validator refuses only a section still to be accepted, and a final refusal keeps the last one: a
        section accepted before the rule would stay in every request. It is set aside (a record and one event), the
        architect reads the locked preamble alone, and the next accepted section is read as ever."""
        locked = self.settings["architect"]["agenda_locked"]
        self.assertTrue(locked)
        stale = "(a) Stop proposing single names.\n" + CLEAN + "\n" + FOREIGN
        section = {"text": stale, "at": "2026-10-02T16:54:19Z", "run": 1}
        self.store.put(AGENDA_KEY, section)
        architect = Architect(self.store, None, self.settings, clock=self.clock)
        # The architect never reads such a section, set aside yet or not.
        title, agenda = architect.agenda()
        self.assertEqual((title, agenda), (LOCKED_AGENDA_TITLE, locked.strip()))
        self.assertNotIn("Stop proposing", architect.prompt())
        strategist = self.strategist(FakeRouter(reply()))
        record = strategist.set_aside_stale()
        self.assertEqual((record["section"], record["why"]), (section, "roots: XLU, LQD: not among the Gym's roots"))
        self.assertIsNone(self.store.get(AGENDA_KEY))
        self.assertEqual(self.store.get(AGENDA_ASIDE_KEY)["section"], section, "kept, on record")
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.strategist"]
        self.assertEqual((event["action"], event["section_at"], event["reasons"]),
                         ("set_aside", "2026-10-02T16:54:19Z", ["roots: XLU, LQD: not among the Gym's roots"]))
        self.assertIsNone(strategist.set_aside_stale(), "once: nothing is stored now")
        self.assertEqual(architect.agenda(), (LOCKED_AGENDA_TITLE, locked.strip()), "the locked preamble alone")
        self.assertFalse(strategist.current()["accepted"], "and the strategist's packet no longer carries it as the section")
        out = strategist.run()
        self.assertTrue(out["accepted"], out.get("reasons"))
        title, agenda = architect.agenda()
        self.assertEqual(title, COMPOSED_AGENDA_TITLE)
        self.assertIn("> " + CLEAN.splitlines()[0], agenda)
        self.assertIsNone(strategist.set_aside_stale(), "a section that passes stays")
        self.assertEqual(self.store.get(AGENDA_KEY)["text"], CLEAN)

    def test_a_section_that_names_none_or_the_rule_switched_off_is_left_alone(self):
        self.store.put(AGENDA_KEY, {"text": CLEAN, "at": "2026-10-02T16:54:19Z", "run": 1})
        strategist = self.strategist(FakeRouter(reply()))
        self.assertIsNone(strategist.set_aside_stale())
        self.store.put(AGENDA_KEY, {"text": CLEAN + "\n" + FOREIGN, "at": "2026-10-02T16:54:19Z", "run": 1})
        self.settings["strategist"]["gym_roots_only"] = False
        self.assertIsNone(strategist.set_aside_stale())
        architect = Architect(self.store, None, self.settings, clock=self.clock)
        self.assertEqual(architect.agenda()[0], COMPOSED_AGENDA_TITLE, "the rule off: the section is read as it was")
        self.assertIsNone(self.store.get(AGENDA_ASIDE_KEY))

    def test_the_pass_sets_a_stale_section_aside_before_anyone_reads_it(self):
        seen: list[str] = []
        strategist = SimpleNamespace(due=lambda: False, set_aside_stale=lambda: seen.append("checked"))
        architect = SimpleNamespace(want=lambda: 1, closed=lambda: None, run=lambda **kw: seen.append("architect") or {"born": []})
        out = Swarm.architect_pass(SimpleNamespace(root=self.store.root, architect=architect, strategist=strategist, clock=self.clock))
        self.assertEqual((seen, out), (["checked", "architect"], {"born": []}))
        strategist.set_aside_stale = lambda: 1 / 0  # a check that fails never stops the pass
        self.assertEqual(Swarm.architect_pass(SimpleNamespace(root=self.store.root, architect=architect, strategist=strategist, clock=self.clock)),
                         {"born": []})


class StaleAgendaAtTheStart(LoopCase):
    def test_the_swarm_sets_a_stale_section_aside_when_it_starts_and_wires_the_park_exemption(self):
        self.settings["architect"]["agenda_locked"] = "1. THE VERIFIER: fixed."
        self.settings["gym"]["roots"] = list(ROOTS)
        (self.root / "swarm.json").write_text(json.dumps({  # the box's file, which every step reads again
            "enabled": True, "gym": self.settings["gym"], "researcher": {"idle_seconds": 0},
            "architect": {"agenda_locked": "1. THE VERIFIER: fixed."}}))
        section = {"text": CLEAN + "\n" + FOREIGN, "at": "2026-10-02T16:54:19Z", "run": 1}
        self.store.put(AGENDA_KEY, section)
        sw = self.swarm()
        self.assertEqual(sw.run(once=True), 0)
        self.assertIsNone(self.store.get(AGENDA_KEY))
        self.assertEqual(self.store.get(AGENDA_ASIDE_KEY)["section"], section)
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.strategist"]
        self.assertEqual((event["action"], event["reasons"]), ("set_aside", ["roots: XLU, LQD: not among the Gym's roots"]))
        self.assertEqual(sw.architect.agenda(), (LOCKED_AGENDA_TITLE, "1. THE VERIFIER: fixed."))
        fam = self.store.families(alive=True)[0]
        self.assertIs(sw.scheduler.owed(fam), False, "wired to the researcher's own reading: nothing is owed a seed")
        with mock.patch.object(sw.researcher, "operator_owed", return_value={"n": 1}):
            self.assertIs(sw.scheduler.owed(fam), True)


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
        """A family whose latest counted validation met `met` checks, with `cycles_now` worked cycles behind it."""
        self.family(fid)
        self.store.update_family(fid, cycles=cycles_now + 7, validated_version=1, validations=1)  # every cycle, failed ones too
        self.store.set_state(fid, validation_line=line(met), validation_version=1,
                             **{VALIDATED_CYCLES_KEY: cycles_then, WORKED_CYCLES_KEY: cycles_now}, **state)
        return self.store.family(fid)

    def work(self, fid, n=1):
        """`n` more cycles the family's researcher worked (`Researcher._count_worked`)."""
        self.store.set_state(fid, **{WORKED_CYCLES_KEY: worked_cycles(self.store.family(fid)) + n})

    def test_five_checks_or_fewer_and_ten_cycles_later_the_family_is_dead(self):
        self.assertEqual((self.settings["researcher"]["retire_short_checks"], self.settings["researcher"]["retire_short_cycles"]),
                         (5, 10))
        fam = self.validated(met=5, cycles_then=20, cycles_now=29)
        self.assertIsNone(idle_dead(fam, self.settings), "nine cycles after it")
        self.assertEqual(short_left(fam, self.settings), 1)
        self.store.bump("a", cycles=50)  # cycles that failed (an outage: no model call, an error each) spend none of the ten
        self.assertIsNone(idle_dead(self.store.family("a"), self.settings))
        self.assertEqual(short_left(self.store.family("a"), self.settings), 1)
        self.work("a")
        fam = self.store.family("a")
        self.assertEqual(idle_dead(fam, self.settings),
                         "kept researching for 10 cycles after a validation that met 5 of the line's 8 checks")
        self.assertEqual(short_left(fam, self.settings), 0)
        self.assertTrue(dead_slot(fam, self.settings))
        # The rule stands by itself: with the idle count and the dormancy clause both off, it still retires.
        for off in ({"retire_idle_evaluations": 0, "dormant_cycles": 0}, {"retire_idle_evaluations": None, "dormant_cycles": None}):
            settings = copy.deepcopy(self.settings)
            settings["researcher"].update(off)
            self.assertIn("kept researching for 10 cycles", idle_dead(fam, settings), off)

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
        self.store.update_family("a", cycles=11, best_train=0.4)
        self.store.set_state("a", **{WORKED_CYCLES_KEY: 7})
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        met, total = checks_met(fam["state"]["validation_line"])
        self.assertEqual((total, fam["state"][VALIDATED_CYCLES_KEY]), (8, 7), "the family's worked cycles when it was judged")
        self.assertLessEqual(met, 5)
        self.work("a", 9)
        self.assertEqual(t.idle_pass()["retired"], [])
        self.work("a")
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
        self.work("a", 6)
        v2 = self.store.add_version("a", "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return [None]\n", {},
                                    author="model")
        self.store.update_family("a", best_version=v2["n"])
        t.validate(self.store.families(alive=True))
        self.assertEqual(self.store.family("a")["state"][VALIDATED_CYCLES_KEY], 6, "a counted validation: from here")
        self.work("a", 6)
        self.store.update_family("a", best_version=1)  # the first version submitted again: judged from its record
        jobs = len(self.pool.jobs)
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        self.assertEqual((len(self.pool.jobs), fam["state"]["validation_version"], fam["state"][VALIDATED_CYCLES_KEY]), (jobs, 1, 6))
        self.assertIsNone(idle_dead(fam, self.settings), "six cycles since the last counted validation")
        self.work("a", 4)
        self.assertIsNotNone(idle_dead(self.store.family("a"), self.settings))


class DepthStatus(ResearcherCase):
    def test_the_researcher_reads_its_countdown(self):
        fid = self.fam["id"]
        self.store.update_family(fid, cycles=40, validated_version=1, validations=1)
        self.store.set_state(fid, validation_line=line(3), validation_version=1, **{VALIDATED_CYCLES_KEY: 20, WORKED_CYCLES_KEY: 23})
        status = self.researcher().status(self.store.family(fid))
        self.assertIn("Validation of version 1: it did not meet the validation line (3 of 8 checks passed).", status)
        self.assertIn("so the idle rule retires your family 7 cycles from now, whatever awaits validation then", status)
        self.store.set_state(fid, validation_line=line(6))
        self.assertNotIn("the idle rule retires your family", self.researcher().status(self.store.family(fid)))

    def test_only_a_cycle_the_researcher_worked_is_counted(self):
        """An outage spends none of the ten: a cycle with no model call, or one that ended in an error, is not counted."""
        fid = self.fam["id"]
        self.researcher().cycle(fid)  # the starter: a run and no model call
        self.assertEqual((self.store.family(fid)["cycles"], worked_cycles(self.store.family(fid))), (1, 0))

        def down(body):
            raise RuntimeError("the provider is down")
        for _ in range(10):
            self.steps = [down]
            out = self.researcher().cycle(fid)
            self.assertIn("error", out)
        fam = self.store.family(fid)
        self.assertEqual((fam["cycles"], worked_cycles(fam)), (11, 0), "ten failed cycles: every one a cycle, none worked")
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing new"})]}]
        out = self.researcher().cycle(fid)
        self.assertNotIn("error", out)
        self.assertEqual(worked_cycles(self.store.family(fid)), 1, "a turn its researcher had")
        self.store.update_family(fid, validated_version=1, validations=1)
        self.store.set_state(fid, validation_line=line(4), validation_version=1, **{VALIDATED_CYCLES_KEY: 1})
        for _ in range(10):
            self.steps = [down]
            self.researcher().cycle(fid)
        self.assertIsNone(idle_dead(self.store.family(fid), self.settings), "ten cycles of an outage retire no one")
        self.assertEqual(short_left(self.store.family(fid), self.settings), 10)


# ------------------------------------------------------------------------ 8. an identical program is validated once
PROGRAM = "NEEDS = {'roots': ['SPY']}\nPARAMS = {'width': 2}\ndef decide(ctx):\n    return []\n"
ROOTLESS = "PARAMS = {'width': 2}\ndef decide(ctx):\n    return []\n"


class ValidatedOnce(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)
        self.image = "sbcp_gym_one"
        self.fill = "fm-1"
        self.pool.image = lambda kind="gym": self.image
        self.pool.bundle = lambda: "bundle-one"
        self.verdict = weak
        # As the Gym's own results are: each says the roots it ran on, its capital and its fill model.
        self.answer = lambda job: {**self.verdict(job), "gym_image": self.image, "gym_bundle": "bundle-one",
                                   "roots": list(job.roots), "capital": self.settings["gym"].get("capital", 10000.0),
                                   "fill_model": self.fill}

    def born(self, fid, *, parent=None, code=PROGRAM, params=None, roots=("SPY",), origin="seed"):
        fam = self.store.add_family({**SPEC, "id": fid, "roots": list(roots)}, origin=origin, parent=parent)
        v = self.store.add_version(fam["id"], code, params or {}, author="operator-revive" if parent else "seed")
        self.store.update_family(fam["id"], best_version=v["n"])
        return fam["id"]

    def tournament(self):
        return Tournament(self.store, self.pool, self.settings, clock=self.clock)

    def round(self):
        return self.tournament().validate(self.store.families(alive=True))

    def n_of(self, fid):
        """The N the family's verdict was judged at (the lineage's validated versions, this one included)."""
        return self.store.family(fid)["state"]["validation_line"]["numbers"]["validated_versions"]

    def test_a_failing_verdict_is_inherited_and_counts_in_the_lineage(self):
        """R7. A revival carries its parent's program unchanged: it reads the parent's result (no job, no trial), the
        verdict fails, and it is one more validated version of the lineage, so N is what its own run would have faced."""
        self.born("a")
        first = self.round()
        self.assertEqual((first["queued"], len(self.pool.jobs)), (1, 1))
        self.assertNotIn("inherited", first)
        parent = self.store.family("a")
        self.assertFalse(parent["state"]["validation_line"]["passed"])
        self.assertEqual((self.n_of("a"), self.store.lineage_validated("a")[0]), (1, 1))
        self.born("a-r", parent="a", origin="operator-revive")
        self.store.set_state("a-r", **{WORKED_CYCLES_KEY: 4})
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs)), (0, 1), "the same program on the same Gym: no second job")
        source = out["inherited"]["a-r"]
        self.assertEqual((source["family"], source["version"]), ("a", 1))
        child = self.store.family("a-r")
        self.assertEqual(child["state"]["validation_inherited"], source)
        self.assertEqual(out["judged"]["a-r"]["inherited"], source)
        self.assertEqual((child["state"]["validation_line"]["passed"], child["state"]["gate_ready"]), (False, False),
                         "only a verdict that fails is read across")
        self.assertEqual((child["validated_version"], child["validations"], child["trials"]), (1, 1, 0),
                         "its validation, with no trial of its own")
        self.assertEqual((child["state"]["validated_trials"], child["state"][VALIDATED_CYCLES_KEY]), (0, 4),
                         "its idle clocks run from the verdict")
        rows = self.store.runs("a-r", window="validation")
        self.assertEqual([(r["trials"], r["stress"], r["summary"]["inherited"]) for r in rows], [(0, 1.5, source), (0, 1.0, source)],
                         "its own copy of the record and of its stress twin, with no trial: nothing was evaluated")
        self.assertEqual((self.n_of("a-r"), self.store.lineage_validated("a-r")[0]), (2, 2),
                         "inheriting never lowers N: the copy is one more validated version of the lineage")
        self.assertEqual(self.store.lineage_trials("a-r"), self.store.lineage_trials("a"), "and no trial")
        self.store.update_family("a-r", validated_version=None)  # submitted again: judged from its own record
        again = self.round()
        self.assertEqual((again["queued"], len(self.pool.jobs)), (0, 1))
        self.assertEqual(self.store.family("a-r")["state"]["validation_inherited"], source, "re-judged: still inherited")
        self.assertEqual((self.store.family("a-r")["validations"], self.n_of("a-r")), (1, 2), "a re-judged record is no new validation")
        self.assertEqual(self.round()["queued"], 0, "validated: nothing is owed next round")
        self.assertIsNone(parent["state"].get("validation_inherited"))
        # Its next version is the lineage's third: judged at N 3, as if the revival had run its own validation.
        v2 = self.store.add_version("a-r", PROGRAM + "# a revision\n", {}, author="model")
        self.store.update_family("a-r", best_version=v2["n"])
        self.assertEqual(self.round()["queued"], 1)
        self.assertEqual((self.n_of("a-r"), self.store.lineage_validated("a-r")[0]), (3, 3))

    def test_a_verdict_that_would_pass_is_never_inherited(self):
        """R7. The parent met the line and the same result would meet it for the revival too: nothing is read across.
        The revival is validated on the running Gym by its own job, at the N its lineage has (2), and only that run
        can put it at the gate."""
        self.verdict = stronger
        self.born("a")
        self.round()
        self.assertTrue(self.store.family("a")["state"]["validation_line"]["passed"])
        self.born("a-r", parent="a", origin="operator-revive")
        t = self.tournament()
        fam = self.store.family("a-r")
        known = t.known_validation(fam, self.store.version("a-r", 1))
        self.assertEqual(known[1]["family"], "a", "the program's result is known")
        self.assertFalse(t.inheritable("a-r", 1, known[0]), "and it would meet the line at N 2")
        self.assertIsNone(t.judge("a-r", 1, known[0], record=False, inherited=known[1]), "so nothing is written from it")
        self.assertEqual((self.store.runs("a-r", window="validation"), self.store.family("a-r")["validated_version"]), ([], None))
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs), self.pool.jobs[-1].family), (1, 2, "a-r"), "its own Gym job")
        self.assertNotIn("inherited", out)
        child = self.store.family("a-r")
        self.assertIsNone(child["state"]["validation_inherited"])
        self.assertEqual((child["trials"], self.n_of("a-r"), self.store.lineage_validated("a-r")[0]), (2, 2, 2),
                         "its run and the stress twin are its trials, and it is judged at N 2")
        self.assertEqual((child["state"]["validation_line"]["passed"], child["state"]["gate_ready"]), (True, True))

    def test_an_inherited_copy_is_never_judged_again_as_a_pass(self):
        """A copy is re-judged from its record when its version is submitted again. Should that verdict ever meet the line
        (the lineage's count moved), the copy is no verdict: the family's own job is made."""
        self.born("a")
        self.round()
        self.born("a-r", parent="a")
        self.round()
        self.assertEqual((self.store.family("a-r")["trials"], len(self.pool.jobs)), (0, 1), "inherited, failing")
        self.store.update_family("a-r", validated_version=None)  # submitted again
        with mock.patch.object(Tournament, "inheritable", return_value=False):  # as if it would meet the line now
            out = self.round()
        child = self.store.family("a-r")
        self.assertEqual((out["queued"], self.pool.jobs[-1].family, child["trials"]), (1, "a-r", 2), "its own Gym run")
        self.assertIsNone(child["state"]["validation_inherited"])
        self.assertEqual(self.n_of("a-r"), 2, "the same (family, version): the count does not move")

    def test_a_pass_elsewhere_that_fails_at_this_lineages_n_is_read_as_the_failure_it_is(self):
        """The verdict is the reading family's, judged at its lineage's N with its copy counted. A program met the line as
        its lineage's first validated version; a family that has already validated a weak version takes up the same
        program (the store links the two lineages by the shared code), and there the same result is the third validated
        version and falls short of the deflated Sharpe. That failing verdict is inherited: its own run would say the same."""
        other = PROGRAM + "# an earlier idea\n"
        self.verdict = lambda job: weak(job) if job.code == other else strong(job)
        self.born("p")
        self.round()
        self.assertEqual((self.store.family("p")["state"]["validation_line"]["passed"], self.n_of("p")), (True, 1))
        self.born("q", code=other)
        self.round()
        self.assertEqual((self.store.family("q")["state"]["validation_line"]["passed"], self.n_of("q")), (False, 1))
        v2 = self.store.add_version("q", PROGRAM, {}, author="model")
        self.store.update_family("q", best_version=v2["n"])
        jobs = len(self.pool.jobs)
        out = self.round()
        self.assertEqual((out["queued"], out["inherited"]["q"]["family"], len(self.pool.jobs)), (0, "p", jobs))
        q = self.store.family("q")
        self.assertEqual((q["state"]["validation_line"]["passed"], q["state"]["gate_ready"]), (False, False),
                         "p's pass at N 1 is no pass for the lineage's third validated version")
        self.assertEqual((self.n_of("q"), self.store.lineage_validated("q")[0]), (3, 3), "p's, q's first, and this copy")
        self.assertFalse(q["state"]["validation_line"]["checks"]["dsr"], "the deflated Sharpe is what it falls short of")
        # A family that validates the same program by itself (the switch off) is judged the same way, one version on.
        self.settings["tournament"]["reuse_validations"] = False
        self.born("r", code=other)
        self.round()
        v2 = self.store.add_version("r", PROGRAM, {}, author="model")
        self.store.update_family("r", best_version=v2["n"])
        out = self.round()
        r = self.store.family("r")
        self.assertEqual((out["queued"], r["state"]["validation_line"]["passed"], self.n_of("r")), (1, False, 5))
        self.assertEqual(q["state"]["validation_line"]["checks"], r["state"]["validation_line"]["checks"],
                         "its own run on the Gym meets the same checks")

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

    def test_the_stored_results_own_roots_capital_and_fill_model_decide(self):
        """A result answers for another family only when it is the evaluation that family's job would be: by the
        result's own record, never by the other family's roots as they stand now."""
        self.born("c", code=ROOTLESS, roots=("SPY",))
        self.round()
        self.store.update_family("c", roots=["QQQ"])  # its researcher moved its roots after the validation
        self.born("e", code=ROOTLESS, roots=("QQQ",))
        out = self.round()
        self.assertNotIn("e", out.get("inherited", {}), "c's result was made on SPY: it says nothing of QQQ")
        self.assertEqual([j.roots for j in self.pool.jobs if j.family == "e"], [("QQQ",)])
        t = self.tournament()
        result_c = self.store.run_result(self.store.runs("c", window="validation")[-1]["run_id"])
        self.assertEqual((result_c["roots"], t.same_evaluation(result_c, ("SPY",)), t.same_evaluation(result_c, ("QQQ",))),
                         (["SPY"], True, False))
        self.assertFalse(t.same_evaluation({k: v for k, v in result_c.items() if k != "roots"}, ("SPY",)),
                         "a result that does not say its roots is no answer")
        # Another capital is another evaluation.
        self.born("h")
        self.round()
        self.settings["gym"]["capital"] = 25000.0
        self.born("i")
        out = self.round()
        self.assertEqual((out["queued"], out.get("inherited", {})), (1, {}), "h's result was run at another capital")
        self.settings["gym"]["capital"] = 10000.0
        self.born("j")
        out = self.round()
        self.assertEqual((out["queued"], out["inherited"]["j"]["family"]), (0, "h"), "the newest result at this capital")
        # A fill model calibrated anew on the box: the stored results are another model's.
        self.assertIsNone(t.fill_model_now(), "no keyed run names one yet")
        self.store.add_run("h", 1, {"run_id": "train-on-new-model", "status": "ok", "trials": 1, "fill_model": "fm-2",
                                    "summary": {"trades": 10}}, window="train", stress=1.0, purpose="train", key="a-key")
        self.assertEqual(t.fill_model_now(), "fm-2")
        self.fill = "fm-2"
        self.born("k")
        out = self.round()
        self.assertEqual((out["queued"], out.get("inherited", {})), (1, {}), "no stored result was made under this fill model")
        self.born("l")
        out = self.round()
        self.assertEqual((out["queued"], out["inherited"]["l"]["family"]), (0, "k"))

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
                         "one job; the twin reads its failing result in the same round")
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
        # A twin whose first's result would meet the line for it is validated by itself, in the same round (R7).
        self.verdict = stronger
        other = PROGRAM + "# another program\n"
        self.born("p", code=other)
        self.born("p-r", parent="p", code=other)
        out = self.round()
        self.assertEqual((out["queued"], out.get("inherited", {}), out.get("waiting_twin", [])), (2, {}, []))
        twin = self.store.family("p-r")
        self.assertEqual((self.pool.jobs[-1].family, twin["trials"], twin["validated_version"], self.n_of("p-r")), ("p-r", 2, 1, 2),
                         "its own Gym run, judged at N 2")
        self.assertEqual((twin["state"]["validation_line"]["passed"], twin["state"]["validation_inherited"]), (True, None))

    def test_a_run_the_gym_did_not_finish_is_never_inherited(self):
        self.verdict = lambda job: {**weak(job), "status": "error"}
        self.born("a")
        self.round()
        self.assertEqual([r["status"] for r in self.store.runs("a", window="validation") if r["stress"] == 1.0], ["error"])
        self.verdict = weak
        self.born("a-r", parent="a")
        # Isolate the child: a full round now retries the interrupted parent and may inherit that completed retry.
        out = self.tournament().validate([self.store.family("a-r")])
        self.assertNotIn("a-r", out.get("inherited", {}), "an error is no answer about the program")
        self.assertEqual([j.family for j in self.pool.jobs].count("a-r"), 1, "it is validated by itself")

    def test_an_unfinished_validation_is_recorded_as_an_error_and_retried(self):
        self.verdict = lambda job: unfinished(job.name, "synthetic worker interruption")
        self.born("a")
        self.store.set_state("a", dormant_cycles=3, **{WORKED_CYCLES_KEY: 7})
        out = self.round()
        fam = self.store.family("a")
        self.assertEqual(out["judged"], {}, "an interrupted worker made no verdict about the program")
        self.assertIn("synthetic worker interruption", out["errors"]["a"])
        self.assertEqual((fam["validated_version"], fam["validations"], fam["trials"]), (None, 0, 0))
        self.assertEqual(fam["state"]["dormant_cycles"], 3, "an error is no new evidence")
        self.assertNotIn(VALIDATED_CYCLES_KEY, fam["state"], "no depth-rule clock starts")
        self.assertNotIn("validation_verdicts", fam["state"], "no failed verdict is invented")
        self.assertEqual(self.store.lineage_validated("a")[0], 0)
        self.assertEqual([r["status"] for r in self.store.runs("a", window="validation")], ["error"])
        self.assertIsNone(self.tournament().recorded_validation("a", 1), "an error record is not a cached answer")
        self.verdict = weak
        out = self.round()
        fam = self.store.family("a")
        self.assertEqual((out["queued"], len(self.pool.jobs), fam["validated_version"], fam["validations"], fam["trials"]),
                         (1, 2, 1, 1, 2), "the same version gets its own completed evaluation")
        self.assertEqual((self.n_of("a"), self.store.lineage_validated("a")[0]), (1, 1))

    def test_an_unfinished_stress_twin_does_not_complete_or_inherit_a_validation(self):
        # The real worker hashes the normal evaluation deterministically, even when only its stress twin failed.
        self.verdict = lambda job: {**weak(job), "run_id": "synthetic-stable-validation",
                                   "stress_1.5": {"status": "error", "reason": "synthetic stress interruption"}}
        self.born("a")
        out = self.round()
        fam = self.store.family("a")
        self.assertEqual(out["judged"], {})
        self.assertIn("synthetic stress interruption", out["errors"]["a"])
        self.assertEqual((fam["validated_version"], fam["validations"], fam["trials"]), (None, 0, 1),
                         "the completed normal-spread trial counts; the interrupted twin does not")
        self.assertEqual(self.store.lineage_validated("a")[0], 1, "an observed normal-spread result still counts in N")
        self.assertEqual([(r["stress"], r["status"], r["trials"]) for r in self.store.runs("a", window="validation")],
                         [(1.5, "error", 0), (1.0, "ok", 1)])
        self.born("a-r", parent="a")
        self.assertIsNone(self.tournament().known_validation(self.store.family("a-r"), self.store.version("a-r", 1)))
        self.verdict = lambda job: {**weak(job), "run_id": "synthetic-stable-validation"}
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs)), (1, 2))
        self.assertEqual(out["inherited"]["a-r"]["family"], "a", "only the completed retry can be read across")
        self.assertEqual((self.store.family("a")["validations"], self.store.family("a-r")["validations"]), (1, 1))
        self.assertEqual(self.store.lineage_validated("a-r")[0], 2, "the retry adds no extra version, the inherited copy does")
        self.assertEqual(self.store.family("a")["trials"], 3, "two completed normal trials and one completed stress twin")
        self.assertEqual(self.store.run_result("synthetic-stable-validation")["stress_1.5"]["status"], "ok")
        self.assertIsNotNone(self.tournament().recorded_validation("a", 1), "the deterministic hash now holds its completed answer")

    def test_a_completed_disqualified_run_is_a_failed_verdict_not_an_outage(self):
        self.verdict = lambda job: {**weak(job), "status": "disqualified"}
        self.born("a")
        out = self.round()
        self.assertEqual((out["judged"]["a"]["passed"], out["errors"], self.store.family("a")["validations"]), (False, {}, 1))
        self.assertEqual(self.round()["queued"], 0, "a completed program failure is not retried as an infrastructure outage")

    def test_a_completion_crash_rolls_back_both_receipts_and_verdict_before_retry(self):
        for stage in ("stress_receipt", "verdict"):
            with self.subTest(crash_after=stage):
                fid = f"crash-{stage.replace('_', '-')}"
                run_id = f"synthetic-stable-{stage}"
                self.verdict = lambda job, rid=run_id: {**weak(job), "run_id": rid,
                                                       "stress_1.5": {"status": "error", "reason": "synthetic interruption"}}
                self.born(fid, code=PROGRAM + f"# {stage}\n")
                self.round()
                before = self.store.family(fid)
                before_rows = self.store.runs(fid, window="validation")
                before_payload = self.store.run_result(run_id)
                self.assertEqual((before["trials"], before["validations"], before["validated_version"]), (1, 0, None))
                self.verdict = lambda job, rid=run_id: {**weak(job), "run_id": rid}
                completed = self.answer(self.pool.jobs[-1])
                tournament = self.tournament()
                target = self.store if stage == "stress_receipt" else tournament
                method = "add_run" if stage == "stress_receipt" else "_verdict"
                original = getattr(target, method)

                def crash_after_write(*args, **kwargs):
                    answer = original(*args, **kwargs)
                    if stage == "verdict" or kwargs.get("stress") == 1.5:
                        raise RuntimeError("synthetic crash after durable-state writes")
                    return answer

                with mock.patch.object(target, method, side_effect=crash_after_write):
                    with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                        tournament.judge(fid, 1, completed)
                self.assertEqual(self.store.family(fid), before, "trial, completion and idle counters roll back together")
                self.assertEqual(self.store.runs(fid, window="validation"), before_rows, "both receipt pointers roll back")
                self.assertEqual(self.store.run_result(run_id), before_payload, "the interrupted payload stays immutable")
                self.assertEqual(self.store.lineage_validated(fid)[0], 1, "the observed normal trial remains in N")
                self.assertIsNone(tournament.recorded_validation(fid, 1), "a failed completion transaction is no cache hit")

                # Retry delivery of this same completed worker response; no new evaluation is requested.
                self.assertIsNotNone(tournament.judge(fid, 1, completed))
                fam = self.store.family(fid)
                self.assertEqual((fam["trials"], fam["validations"], fam["validated_version"]), (3, 1, 1))
                self.assertEqual([(r["stress"], r["status"], r["trials"]) for r in self.store.runs(fid, window="validation")],
                                 [(1.5, "ok", 1), (1.0, "ok", 2)], "normal retry and completed stress trial both persist")
                self.assertEqual(self.store.run_result(run_id)["stress_1.5"]["status"], "ok")
                self.assertEqual(self.store.lineage_validated(fid)[0], 1, "a retry is still the same version")
                trials, jobs = fam["trials"], len(self.pool.jobs)
                self.assertEqual(self.round()["queued"], 0, "only the fully committed completion is reused")
                self.assertEqual((self.store.family(fid)["trials"], len(self.pool.jobs)), (trials, jobs))

    def test_the_switch_validates_every_family_by_itself(self):
        self.settings["tournament"]["reuse_validations"] = False
        self.born("a")
        self.round()
        self.born("a-r", parent="a")
        out = self.round()
        self.assertEqual((out["queued"], len(self.pool.jobs)), (1, 2))
        self.assertNotIn("inherited", out)
        self.assertIsNone(self.store.family("a-r")["state"]["validation_inherited"])
        self.assertEqual(self.n_of("a-r"), 2, "the same N either way")

    def test_an_inherited_short_verdict_starts_the_depth_rules_count(self):
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        self.born("a")
        self.round()
        self.born("a-r", parent="a")
        self.round()
        child = self.store.family("a-r")
        self.assertLessEqual(checks_met(child["state"]["validation_line"])[0], 5)
        self.assertEqual(short_left(child, self.settings), 10)
        self.store.set_state("a-r", **{WORKED_CYCLES_KEY: 10})
        self.assertIn("kept researching for 10 cycles", idle_dead(self.store.family("a-r"), self.settings))


# ------------------------------------------------------------------------------------------------ 9. the cells' pace
class ThePace(CardCase):
    """THE CELLS' PACE, on (as policy.json ships it): every carded birth counts against its cell and the hour."""

    CELLS = [(c, h) for c in cards.MECHANISM_CLASSES for h in cards.HOLDING]

    def setUp(self):
        super().setUp()
        self.settings["architect"].update(structures=list(ALLOWED), claimable_rows=2, max_rebirths_per_cell=12, pace_births=True)
        self.settings["population"].update(start=2000, ceiling=2000)
        self.n = 0

    def card(self, c="trend_momentum", h="days_4_10"):
        card, errors = cards.validate({**CARD, "mechanism_class": c, "holding": h})
        self.assertEqual(errors, [])
        return card

    def bear(self, card) -> str:
        """A carded birth, as the architect's admission stores one."""
        self.n += 1
        fam = self.store.add_family({"id": f"born-{self.n}", "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"],
                                     "card_sha": cards.card_sha(card)}, origin="architect")
        cards.put(self.store, fam["id"], card, "debit_vertical")
        return fam["id"]

    def index(self):
        return cards.RebirthIndex(self.store, self.settings)

    def test_a_cell_bears_one_birth_each_fourteen_hours_claimed_or_not(self):
        card, cell = self.card(), ("trend_momentum", "directional", "days_4_10")
        index = self.index()
        self.assertEqual(index.pace_seconds, 14 * 3600, "the window over the cell budget: 7 days over 12")
        self.assertEqual(index.check(card, "debit_vertical"), {"ok": True, "matched": []}, "a cell with no row needs no claim")
        self.bear(card)
        index = self.index()
        refused = index.check(card, "debit_vertical")
        self.assertEqual((refused["ok"], refused["paced"]), (False, True), "the same idea in the same cell, with no claim to spend")
        self.assertEqual(refused["reason"], "the cell trend_momentum / directional / days_4_10 bore a birth 0.0 hours ago and "
                                            "bears its next in 14.0 hours (a cell bears one birth each 14 hours, claimed or "
                                            "not): look in another cell")
        self.assertTrue(index.check(self.card(h="days_1_3"), "debit_vertical")["ok"], "another cell bears")
        self.assertFalse(index.bearable(cell, []))
        self.assertEqual(index.grid(("directional",))[-1][0], cell, "a held cell is listed last")
        [line] = [x for x in index.cells(claimable=2, families=("directional",)) if x.startswith("trend_momentum / directional / days_4_10")]
        self.assertEqual(line, "trend_momentum / directional / days_4_10: no row: a card here needs no rebirth; paced: it bore "
                               "a birth lately, none here for 14.0 more hours")
        self.clock.advance(14 * 3600 - 1)
        self.assertFalse(self.index().check(card, "debit_vertical")["ok"], "a second short of its time")
        self.clock.advance(1)
        index = self.index()
        self.assertTrue(index.check(card, "debit_vertical")["ok"])
        index.note_birth(card, "debit_vertical")  # born in this pass: the pace binds within a pass too
        self.assertTrue(index.check(card, "debit_vertical")["paced"])

    def test_a_claimed_rebirth_is_paced_too_and_the_switch_restores_the_budget_alone(self):
        dead = self.bury("rebound-old", self.card("reversal_liquidity", "days_1_3"), reason="Refuted: the fade loses after costs.")
        reborn = {**CARD, "inputs": ["clock", "open_interest", "underlying_price"], "rebirth": {"row": dead, **GOOD}}
        words = "Dealer inventory imbalance after late selling predicts which rebounds complete next session."
        card, errors = cards.validate(reborn)
        self.assertEqual(errors, [])
        refused = self.index().check(card, "debit_vertical", words, [0, 5])
        self.assertEqual((refused["ok"], refused["paced"], refused["row"]), (False, True, dead),
                         "the dead family's own birth is the cell's newest: a valid claim waits out the pace")
        self.clock.advance(14 * 3600)
        index = self.index()
        self.assertTrue(index.check(card, "debit_vertical", words, [0, 5])["rebirth"])
        index.note_birth(card, "debit_vertical")
        self.assertTrue(index.check(card, "debit_vertical", words, [0, 5])["paced"])
        for off in (False, None, 1, "true"):  # only JSON true is on: the code's default (the key absent) is the budget alone
            self.settings["architect"]["pace_births"] = off
            self.assertIsNone(self.index().pace_seconds, off)
        del self.settings["architect"]["pace_births"]
        index = self.index()
        self.assertIsNone(index.pace_seconds)
        for _ in range(2):  # the budgets alone, as before: as many as the row may back, in one instant
            self.assertTrue(index.check(card, "debit_vertical", words, [0, 5])["ok"])
            index.note_birth(card, "debit_vertical")
        self.assertIn("has already backed 2 rebirth(s)", index.check(card, "debit_vertical", words, [0, 5])["reason"])
        self.assertEqual((index.hour_cap(44), index.hour_room(44)), (None, None))
        self.settings["architect"].update(pace_births=True, max_rebirths_per_cell=0)
        self.assertIsNone(self.index().pace_seconds, "no budget, no pace: a cell with no room bears no claimed rebirth anyway")

    def test_the_hour_bears_the_cells_budget_spread_over_the_window_and_a_spent_hour_asks_no_model(self):
        index = self.index()
        self.assertEqual((index.hour_cap(44), index.hour_room(44)), (3, 3), "44 cells x 12 a week over 168 hours, rounded down")
        router = Asked()
        arch = Architect(self.store, router, self.settings, clock=self.clock)
        rows = [proposal(f"idea-{i}", card={**CARD, "mechanism_class": c, "holding": h}, roots=[root],
                         mechanism=f"Invented idea number {i}: a slow adjustment that persists for several sessions on {root}.")
                for i, ((c, h), root) in enumerate(zip(self.CELLS[:5], ("SPY", "QQQ", "IWM", "XSP", "SPXW")))]
        born = arch.admit(rows)
        self.assertEqual(len(born), 3, "five proposals in five open cells: the hour bears three")
        self.assertEqual(arch.card_refused, [], "the hour's cap is no refusal of a card")
        closed = arch.closed()
        self.assertEqual(closed, {"cells": 44, "hour": {"born": 3, "cap": 3}})
        self.clock.advance(60)
        out = arch.run()
        self.assertEqual((out["skipped"], out["cells"], router.calls), (SKIPPED_PACED, closed, []), "no model is asked")
        self.assertIn("the swarm has borne its births of the hour", out["why"])
        self.assertEqual(self.store.get("architect_at"), self.clock())
        self.clock.advance(3600)
        self.assertIsNone(arch.closed(), "the hour moved on")
        self.assertEqual(arch.room_seen, {"cells": 44, "bearable": 41, "rebirths_left": 44 * 12, "paced": 3, "hour_left": 3,
                                          "hour_cap": 3}, "what the pass's event carries: the funnel sees the wall coming")
        out = arch.run()  # the model is asked (this router answers nothing): the event says what room the cells had
        self.assertEqual(len(router.calls), 1)
        self.settings["architect"]["max_rebirths_per_cell"] = 6
        self.assertEqual(self.index().hour_cap(44), 1, "never under one an hour")

    def test_the_budget_lasts_the_window_and_no_day_bears_nothing(self):
        """The standstill by the budget cannot come back. An architect that lands every proposal it may (the worst
        case) bears the cells' budget evenly: the same number every day, and never more than a cell's budget in any
        window. Before the pace it spent every slot in three days and bore nothing until the window moved."""
        hours: list[int] = []
        times: dict[tuple, list[float]] = {}
        for _ in range(9 * 24):
            index = self.index()
            room, born = index.hour_room(44), 0
            for c, h in self.CELLS:
                if born >= room:
                    break
                card = self.card(c, h)
                if index.check(card, "debit_vertical")["ok"]:
                    self.bear(card)
                    index.note_birth(card, "debit_vertical")
                    times.setdefault((c, h), []).append(self.clock())
                    born += 1
            hours.append(born)
            self.clock.advance(3600)
        days = [sum(hours[d * 24:(d + 1) * 24]) for d in range(9)]
        self.assertEqual(days, [72] * 9, "three an hour, every hour of every day")
        self.assertLessEqual(72 * 7, 44 * 12, "inside the cells' whole budget for the window")
        for cell, at in times.items():
            self.assertTrue(all(b - a >= 14 * 3600 for a, b in zip(at, at[1:])), cell)
            self.assertTrue(all(sum(1 for t in at if start <= t < start + 7 * 86400) <= 12 for start in at), cell)

    def test_the_pass_event_counts_a_paced_refusal_apart(self):
        card = self.card()
        self.bear(card)
        self.clock.advance(3601)  # the hour is free again; the cell is not

        class Proposes:
            def ask(self, **kw):
                return {"route": "sail", "model": "m", "cost_usd": 0.01, "usage": {}, "json": {"families": [
                    proposal("again", card={**CARD, "mechanism_class": "trend_momentum", "holding": "days_4_10"},
                             mechanism="A slow continuation after a breakout persists for several sessions on the ETF.")]}}
        out = Architect(self.store, Proposes(), self.settings, clock=self.clock).run()
        self.assertEqual((out["born"], out["card_refused"]["paced"], out["card_refused"]["rebirth"]), ([], 1, 0))
        self.assertEqual(out["room"]["paced"], 1)


# ------------------------------------------------------------------------------------------ 10. a thin retirement
class ThinRetirement(CardCase):
    """R3. A family its own researcher retired with under ten trials, or with no eligible Train version, files no
    refuting row: the cell's claim requirement and its yield tally stay as they were."""

    CELL = ("trend_momentum", "directional", "days_4_10")

    def setUp(self):
        super().setUp()
        self.card, errors = cards.validate({**CARD, "mechanism_class": "trend_momentum", "holding": "days_4_10"})
        self.assertEqual(errors, [])

    def family(self, fid, *, trials=0, eligible=False, traded=False):
        fam = self.store.add_family({"id": fid, "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"],
                                     "card_sha": cards.card_sha(self.card)}, origin="architect")
        cards.put(self.store, fam["id"], self.card, "debit_vertical")
        if traded or eligible:
            self.store.add_run(fid, 1, {"run_id": f"train-{fid}", "status": "ok", "trials": 1,
                                        "summary": {"trades": 90 if eligible else 9, "train_eligible": eligible}},
                               window="train", stress=1.0, purpose="train")
        self.store.update_family(fid, trials=trials)
        return self.store.family(fid)

    def retire(self, fam, reason="The Gym's data cannot locate the signal: nothing to test."):
        """As the retire tool files it (`Researcher._execute`)."""
        thin = thin_evidence(self.store, fam, self.settings)
        filed = f"Self-refuted by its researcher: {reason}" if thin is None else thin_cause(thin, reason)
        self.assertEqual(self.store.retire_gym(fam["id"], filed, floor=0, source="researcher")["status"], "retired")
        gone = self.store.family(fam["id"])
        return thin, tag_of({"family": fam["id"], "lesson": ""}, gone), gone["retire_reason"]

    def needs_claim(self):
        return not cards.RebirthIndex(self.store, self.settings).check(self.card, "debit_vertical")["ok"]

    def test_what_is_thin(self):
        cases = {"untested": (dict(trials=4), "untested", "IDLE"),
                 "traded, never eligible": (dict(trials=40, traded=True), "thin", "THIN"),
                 "an eligible run and too few trials": (dict(trials=9, eligible=True), "thin", "THIN"),
                 "tested": (dict(trials=10, eligible=True), None, "SELF-REFUTED")}
        for i, (name, (kw, screen, tag)) in enumerate(cases.items()):
            fam = self.family(f"f{i}", **kw)
            self.assertEqual(thin_evidence(self.store, fam, self.settings), screen, name)
            thin, got, reason = self.retire(fam)
            self.assertEqual((thin, got), (screen, tag), name)
            self.assertEqual(reason.startswith(THIN_RETIRED), screen is not None, name)
            self.assertEqual(got in cards.MECHANISM_VERDICTS, screen is None, name)
            self.assertIn("The Gym's data cannot locate the signal", reason, "its researcher's reason is kept")
        self.settings["researcher"]["retire_hold_trials"] = 0  # 0 trials leaves the eligible version alone
        self.assertIsNone(thin_evidence(self.store, self.family("zero", trials=1, eligible=True), self.settings))
        self.assertEqual(thin_evidence(self.store, self.family("none", trials=99), self.settings), "untested")

    def test_a_thin_drift_or_stress_retirement_leaves_no_refuting_row(self):
        self.settings["architect"]["cell_yield"] = True
        since = "2026-01-01T00:00:00Z"
        for fid, mark in (("drift", {"drift_failed": {"1": "synthetic negative Train alpha"}}),
                          ("stress", {"robust_failed": [1], "robust_why": {"1": "lost money on Train at 1.5x the half-spread"}})):
            with self.subTest(screen=fid):
                self.family(fid, trials=4, eligible=True)
                self.store.set_state(fid, **mark)
                self.assertEqual(thin_evidence(self.store, self.store.family(fid), self.settings), fid)
                thin, tag, reason = self.retire(self.store.family(fid))
                self.assertNotIn(tag, cards.MECHANISM_VERDICTS, "fewer than ten trials is a slot freed, even after a screen")
                self.assertIn(f"Idle verdict {fid.upper()}", reason, "the Train record remains in its explanation")
                self.assertFalse(self.needs_claim())
                self.assertEqual(cards.RebirthIndex(self.store, self.settings).rows, [])
        self.assertEqual(cards.cell_yields(self.store, self.settings, since)[self.CELL],
                         {"births": 0, "passed": 0, "pending": 0, "unknown": 2}, "retirement does not invent Train outcomes")

    def test_a_previously_filed_thin_screen_row_still_closes_no_cell_after_restart(self):
        for screen in ("drift", "stress"):
            self.family(screen, trials=4, eligible=True)
            old_reason = f"{THIN_RETIRED}. Idle verdict {screen.upper()}: a synthetic screen failure. Its researcher's reason: done."
            self.assertEqual(self.store.retire_gym(screen, old_reason, floor=0, source="researcher")["status"], "retired")
            self.assertEqual(tag_of({"family": screen}, self.store.family(screen)), screen.upper(), "the historical explanation stays")
        self.assertEqual(cards.RebirthIndex(self.store, self.settings).rows, [], "the explicit thin marker wins over a screen tag")
        self.assertFalse(self.needs_claim())

    def test_a_thin_retirement_leaves_the_cells_claim_requirement_and_its_yield_as_they_were(self):
        self.assertFalse(self.needs_claim(), "a cell with no refuting row: a card there needs no rebirth")
        self.settings["architect"]["cell_yield"] = True
        since = "2026-01-01T00:00:00Z"
        self.family("thin-one", trials=4)
        before = cards.cell_yields(self.store, self.settings, since)
        self.assertEqual(before[self.CELL], {"births": 0, "passed": 0, "pending": 1, "unknown": 0})
        _, tag, _ = self.retire(self.store.family("thin-one"))
        self.assertEqual(tag, "IDLE")
        self.assertFalse(self.needs_claim(), "a slot freed closes no cell")
        self.assertEqual([r["row"] for r in cards.RebirthIndex(self.store, self.settings).rows], [], "no refuting row")
        self.assertEqual(cards.cell_yields(self.store, self.settings, since)[self.CELL],
                         {"births": 1, "passed": 0, "pending": 0, "unknown": 0},
                         "the yield counts it exactly as it counts the same family's idle-rule death: a settled birth")
        # The idle rule's death of the same family is filed the same way: the two exits agree.
        self.family("idle-one", trials=4)
        self.store.retire_gym("idle-one", f"It made no new Gym evaluation in its last 12 cycles. {idle_cause('untested')}",
                              floor=0, source="tournament")
        self.assertEqual(tag_of({"family": "idle-one", "lesson": ""}, self.store.family("idle-one")), "IDLE")
        self.assertEqual(cards.cell_yields(self.store, self.settings, since)[self.CELL]["births"], 2)
        # A tested self-refutation is the finding it was: it closes the cell.
        self.settings["architect"]["cell_yield"] = None
        self.retire(self.family("tested", trials=12, eligible=True), "Refuted: the continuation is priced in every year.")
        self.assertTrue(self.needs_claim())


class ThinRetirementByTheTool(ResearcherCase):
    def test_the_retire_tool_files_a_thin_retirement_by_the_train_record(self):
        self.settings["population"].update(start=50, floor=0)
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)  # traded, never eligible
        self.pool.cancel_family = lambda fid: None
        fid = self.fam["id"]
        self.researcher().cycle(fid)  # the starter: one ineligible run
        self.store.set_state(fid, hold_streak=3)
        reason = "The Gym's data cannot locate the signal: nothing to test."
        self.steps = [{"calls": [("retire", {"reason": reason})]}, {"text": "done"}]
        out = self.researcher().cycle(fid)
        self.assertEqual((out["retired"], out["retire_thin"]), (True, "thin"))
        gone = self.store.family(fid)
        self.assertEqual(gone["retire_reason"], thin_cause("thin", reason))
        self.assertTrue(gone["retire_reason"].startswith(f"{THIN_RETIRED}. Idle verdict THIN, a tested finding"))
        self.assertEqual(tag_of({"family": fid, "lesson": ""}, gone), "THIN")
        self.assertNotIn("THIN", cards.MECHANISM_VERDICTS)
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(event["cause"], f"{THIN_RETIRED}.", "the public cause carries no figure and none of its notes")


# ------------------------------------------------------------------------------------- 11. the extension hold's age
class ExtensionAge(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)
        self.settings["researcher"]["dormant_cycles"] = 3
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)

    def held(self, fid="a", **state):
        self.family(fid)
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))
        self.store.update_family(fid, validated_version=1, validations=1)
        self.store.set_state(fid, validation_line=line(6), validation_version=1, dormant_cycles=40, hold_streak=40,
                             extension_hold={"version": 1, "checks": "6/8", "at": at}, extension_versions=[1], **state)
        return self.store.family(fid)

    def test_a_hold_nobody_cleared_ends_by_its_age_and_the_family_is_an_ordinary_one_again(self):
        self.assertEqual(self.settings["researcher"]["extension_hold_days"], 7)
        fam = self.held()
        self.assertTrue(extension_held(fam))
        self.assertEqual((idle_dead(fam, self.settings), dead_slot(fam, self.settings)), (None, False),
                         "held: no rule retires it, however long it only waits")
        tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        self.clock.advance(7 * 86400 - 60)
        self.assertEqual(tournament.idle_pass()["retired"], [])
        self.assertTrue(extension_held(self.store.family("a")), "inside its days the hold stands")
        self.clock.advance(60)
        [row] = tournament.idle_pass()["retired"]
        self.assertIn("made no new Gym evaluation in its last 40 cycles", row["why"])
        gone = self.store.family("a")
        self.assertEqual((gone["state"]["extension_hold"], gone["state"]["extension_lapsed"]["why"], gone["state"]["extension_versions"]),
                         (None, "age", [1]), "the hold is on record as lapsed, and the same Gym does not hold the version again")
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                   and e["payload"].get("action") == "extension_lapsed"]
        self.assertEqual((event["version"], event["why"], event["days"]), (1, "age", 7.0))

    def test_what_the_age_never_ends(self):
        for fid, state in (("gated", {"gate_ready": True}), ("looking", {"look_inflight": {"sha": "x"}}),
                           ("waiting", {UNIT_WAIT_KEY: {"version": 1, "limit": 100.0}})):
            self.held(fid, **state)
        self.held("plain")
        self.clock.advance(30 * 86400)
        for fid in ("gated", "looking", "waiting"):
            self.assertFalse(lapse_extension(self.store, fid, self.settings, clock=self.clock), fid)
            self.assertTrue(extension_held(self.store.family(fid)), "its version is at the gate, or waits before it for its unit")
        for off in (0, None, -1, True, "many", float("nan")):
            settings = copy.deepcopy(self.settings)
            settings["researcher"]["extension_hold_days"] = off
            self.assertFalse(lapse_extension(self.store, "plain", settings, clock=self.clock), off)
        self.assertTrue(lapse_extension(self.store, "plain", self.settings, clock=self.clock))
        self.assertFalse(lapse_extension(self.store, "plain", self.settings, clock=self.clock), "once")


if __name__ == "__main__":
    unittest.main()

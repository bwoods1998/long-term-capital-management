"""RELEASE F1 WHERE THE RESEARCH STREAM MEETS THE FAST LANE (Oct 3, 2026).

The research stream was built on a tree whose gate made no sealed look; the fast lane made the look the route to Probe
and turned its power hold into a wait. Each stream pins its own half (`test_swarm_f1_research`, `test_swarm_f1_gate_ready`,
`test_fast_lane`, `test_swarm_look_holds`). Here are the places the two touch, on the merged tree with its own switches:

- AS SHIPPED the gate makes the sealed look, so the screens that mirror its holds are ON: the drift carrier screen at
  the gate's own share, and the bar a researcher reads at the count of looks (`researcher.gate_looks`).
- TWO WAITS. A version that met the line with a one-lot unit over what a Probe may hold waits BEFORE the gate
  (`Tournament._verdict`, the research stream); a version the holdout cannot yet judge waits AT the gate under the gate's
  own marker (`Gate.wait_look`, the fast lane). One version can carry both marks (it waited at the gate, and was then
  judged again with its unit over the limit). The earlier stage holds: it has no place at the gate, nothing is paid
  for it, and when the limit moves it comes to the gate again and waits there as before, with no second wait counted.
- A SELECTION GIVEN BACK by a league/live-only adoption is given no gate place while its unit waits
  (`evaluator._look_owed`), and no incubator review is paid for such a version (`incubator.due_reviews`).
- THE EXTENSION HOLD's age limit (the research stream) never ends a hold while its version is at the gate; a version
  that waits there for the look's bar is at the gate, under the gate's own marker.
- THE DEPTH RULE's count of the cycles a researcher worked is no selection key: an adoption leaves it as it is, and a
  mark left from before an adoption of a new Gym retires nobody (the validation it marked is gone with the selection).

Every figure is invented."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from league.swarm import evaluator, evidence, incubator
from league.swarm import gate as G
from league.swarm import settings as S
from league.swarm.gate import LOOK_WAIT, WAIT_OVER_WORDS, waiting
from league.swarm.researcher import (UNIT_WAIT_KEY, VALIDATED_CYCLES_KEY, WORKED_CYCLES_KEY, carrier_share, extension_held,
                                     gate_looks, lapse_extension, power_bar, short_dead, short_left, unit_waiting,
                                     worked_cycles)
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.swarm_fakes import drift_block
from league.tests.test_swarm_incubator import GateCase, SESSIONS
from league.tests.test_swarm_look_holds import PASS, STRONG_SHARPE, THIN_SHARPE, HoldCase
from league.tests.test_swarm_program_bar import GymCase
from league.tests.test_swarm_rounds import strong


class AsShipped(unittest.TestCase):
    def test_the_gate_makes_the_sealed_look_so_the_screens_that_mirror_its_holds_are_on(self):
        """No switch is patched here: the tree's own `gate.SEALED_LOOKS`, the code's defaults and the release's
        policy.json."""
        self.assertIs(G.SEALED_LOOKS, True, "release F1 ships the sealed look as the route to Probe")
        self.assertTrue(gate_looks())
        self.assertTrue(REAL_POLICY_PATH.exists())
        for settings in (copy.deepcopy(S.DEFAULTS), S.load(None, config={})):
            share, min_power = G.look_hold_settings(settings)
            self.assertEqual((share, min_power), (evidence.LOOK_HOLD_DRIFT_SHARE, evidence.LOOK_HOLD_MIN_POWER))
            self.assertEqual(carrier_share(settings), share, "the carrier screen is on, at the gate's own share")
            with tempfile.TemporaryDirectory() as tmp:
                store = SwarmStore(Path(tmp))
                try:
                    bar = power_bar(store, settings)
                    self.assertIsNotNone(bar, "the bar a researcher reads is printed")
                    self.assertEqual((bar["looks"], bar["level"], bar["min_power"], bar["sessions"]),
                                     (0, evidence.HOLDOUT_ALPHA, min_power, G.holdout_sessions()))
                    self.assertGreaterEqual(evidence.holdout_power(bar["sharpe"], bar["sessions"], bar["level"]), min_power)
                finally:
                    store.close()


class TwoWaits(HoldCase):
    """`HoldCase`: the gate's holds at their defaults, a Validation run that meets the line (its one-lot unit 60, the
    fake Gym's), a Train run that leans on no drift."""

    def marks(self, fid: str = "a") -> tuple:
        state = self.store.family(fid)["state"]
        return bool(state.get("gate_ready")), state.get(UNIT_WAIT_KEY), (state.get(LOOK_WAIT) or {}).get("n")

    def wait_events(self) -> int:
        return len([e for e in self.store.events_after(0) if e["kind"] == "swarm.gate"
                    and e["payload"].get("action") == "look_wait"])

    def test_a_version_that_waits_for_its_unit_holds_no_place_under_the_gates_own_marker(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.assertEqual(self.gate.run()["look_waiting"], ["a"], "the holdout cannot judge it yet: it waits at the gate")
        self.assertEqual((self.marks(), self.wait_events()), ((False, None, n), 1))
        self.assertIsNotNone(waiting(self.store.family("a")["state"]))
        # The limit a first real-money position may risk falls under its unit, and the tournament judges it again.
        self.settings["researcher"]["max_unit_usd"] = 50
        tournament = Tournament(self.store, self.pool, self.settings)
        row = tournament.judge("a", n, tournament.recorded_validation("a", n), record=False)
        self.assertEqual((row["passed"], row.get("unit_wait")), (True, True))
        state = self.store.family("a")["state"]
        self.assertEqual(self.marks(), (False, {"version": n, "limit": 50.0}, n), "both marks: the gate's is kept")
        self.assertEqual(unit_waiting(state), {"version": n, "limit": 50.0})
        self.assertIsNone(waiting(state), "it waits before the gate: no place at it")
        # Whatever the gate's own holds say now, no round takes it up: nothing judged, nothing paid, nothing written.
        self.settings["gate"]["look_holds"] = None
        paid = self.paid()
        for _ in range(2):
            self.clock.advance(300)
            out = self.gate.run()
            self.assertEqual((out["look_waiting"], out["looked"], out["refused"], out["look_held"], out["waiting"]),
                             ([], [], [], [], []))
        self.assertEqual((self.paid() - paid, self.holdout_jobs(), self.store.looks(), self.store.refusals("a"),
                          self.store.look_holds("a")), (0, [], [], [], []))
        self.assertEqual(self.marks(), (False, {"version": n, "limit": 50.0}, n))
        # The limit moves back over its unit: the tournament sends it on, and the gate judges it from the top. The
        # holdout still cannot judge it, so it waits at the gate again: no second wait is counted, nothing is paid.
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}
        self.settings["researcher"]["max_unit_usd"] = 100
        again = tournament.validate(self.store.families(alive=True))
        self.assertEqual((again["queued"], self.marks()), (0, (True, None, n)), "no new validation run")
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["looked"], self.marks(), self.wait_events(), self.paid() - paid),
                         (["a"], [], (False, None, n), 1, 0))
        # And when the look's bar allows, it gets its review, its audit and its one look, as any waiting version.
        self.settings["gate"]["look_holds"] = None
        told: list[str] = []
        real = self.gate.tell
        self.gate.tell = lambda fid, text, **kw: told.append(text) or real(fid, text, **kw)
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(([x["family"] for x in out["looked"]], told[0], len(self.store.looks())), (["a"], WAIT_OVER_WORDS, 1))

    def test_the_extension_hold_does_not_end_by_its_age_while_its_version_waits_at_the_gate(self):
        """`researcher.lapse_extension` (the research stream): an extension hold nobody cleared ends after
        `researcher.extension_hold_days`, never while its version is at the gate. The fast lane keeps a waiting
        version's place under the gate's own marker with `gate_ready` cleared: it is at the gate all the same, so its
        family is not made an ordinary one (and retired by the dormancy clause) while its line pass waits for a look."""
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.ready("b", sharpe=THIN_SHARPE)
        self.assertEqual(sorted(self.gate.run()["look_waiting"]), ["a", "b"])
        for fid in ("a", "b"):
            self.assertTrue(extension_held(self.store.family(fid)), "a line pass meets every check: held")
            self.assertFalse(self.store.family(fid)["state"]["gate_ready"])
        self.store.set_state("b", **{LOOK_WAIT: None})  # the control: the same hold with no place at the gate
        self.clock.advance(30 * 86400)
        self.assertFalse(lapse_extension(self.store, "a", self.settings, clock=self.clock))
        self.assertTrue(extension_held(self.store.family("a")))
        self.assertTrue(lapse_extension(self.store, "b", self.settings, clock=self.clock))
        self.assertEqual(self.store.family("b")["state"]["extension_lapsed"]["why"], "age")
        # Once the gate is done with it (its look made), the hold ends by its age like any other.
        self.settings["gate"]["look_holds"] = None
        self.replies = [PASS, PASS]
        self.assertEqual([x["family"] for x in self.gate.run()["looked"]], ["a"])
        self.assertIsNone(waiting(self.store.family("a")["state"]))
        self.assertEqual(n, self.store.family("a")["state"]["validation_version"])
        if extension_held(self.store.family("a")):  # (a failed look leaves the family in the Gym band, its hold as it was)
            self.assertTrue(lapse_extension(self.store, "a", self.settings, clock=self.clock))

    def test_a_ready_place_beside_a_unit_wait_is_never_taken_up(self):
        """A belt (`Gate.run`): no writer leaves `gate_ready` beside the tournament's unit mark, and a state that held
        both all the same gets no review, no audit and no look until the tournament itself sends it on."""
        n = self.ready("a", sharpe=STRONG_SHARPE)
        self.store.set_state("a", **{UNIT_WAIT_KEY: {"version": n, "limit": 50.0}})
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual((out["looked"], out["look_waiting"], out["refused"], self.paid(), self.holdout_jobs()), ([], [], [], 0, []))
        self.assertTrue(self.store.family("a")["state"]["gate_ready"], "left as it was")
        # A mark that names another version than the one validated is no wait (it outlived its validation).
        self.store.set_state("a", **{UNIT_WAIT_KEY: {"version": n + 1, "limit": 50.0}})
        self.assertIsNone(unit_waiting(self.store.family("a")["state"]))
        self.assertEqual([x["family"] for x in self.gate.run()["looked"]], ["a"])

    def test_what_a_unit_wait_is(self):
        line = {"passed": True}
        for state, waits in (({UNIT_WAIT_KEY: {"version": 2, "limit": 100.0}, "validation_version": 2}, True),
                             ({UNIT_WAIT_KEY: {"version": 2, "limit": 100.0, "unknown": True}, "validation_version": 2}, True),
                             ({UNIT_WAIT_KEY: {"version": 2}, "validation_version": 3}, False),
                             ({UNIT_WAIT_KEY: {"version": 2}, "validation_version": None}, False),
                             ({UNIT_WAIT_KEY: {"version": True}, "validation_version": True}, False),
                             ({UNIT_WAIT_KEY: None, "validation_version": 2}, False),
                             ({UNIT_WAIT_KEY: "yes", "validation_version": 2}, False), ({}, False)):
            self.assertEqual(unit_waiting(state) is not None, waits, state)
            marker = {LOOK_WAIT: {"sha": "s" * 64, "n": state.get("validation_version"), "stage": "x", "at": 1.0},
                      "validation_line": line, **state}
            if isinstance(state.get("validation_version"), int) and not isinstance(state.get("validation_version"), bool):
                self.assertEqual(waiting(marker) is None, waits, "the gate's wait holds a place only without a unit wait")
        for garbage in (None, [], "state", 7):
            self.assertIsNone(unit_waiting(garbage))


class ASelectionGivenBack(GymCase):
    def test_no_gate_place_is_given_back_to_a_version_that_waits_for_its_unit(self):
        """`evaluator._look_owed`: a selection a league/live-only adoption gives back gets its gate place when the
        tournament's own rule would give it one. The unit mark is no selection key, so it stands through the adoption:
        while it names the version given back, the tournament's rule gives no place, and neither does the adoption."""
        self.holder("a")
        self.train_run("a", "train-a")
        self.validate("a")
        expected = dict(self.store.get(evaluator.KEY))
        state = self.store.family("a")["state"]
        self.assertTrue(state["gate_ready"])
        cut = {**state, "gate_ready": False}  # as an earlier adoption archived a look in flight: no place, no marker
        self.assertTrue(evaluator._look_owed(self.store, "a", cut, expected), "the control: the look is owed again")
        self.assertFalse(evaluator._look_owed(self.store, "a", {**cut, UNIT_WAIT_KEY: {"version": 1, "limit": 50.0}}, expected),
                         "it waits before the gate for its unit: the tournament sends it on when the limit moves")
        self.assertTrue(evaluator._look_owed(self.store, "a", {**cut, UNIT_WAIT_KEY: {"version": 9, "limit": 50.0}}, expected),
                        "a mark of another version is no wait of this one")
        self.assertNotIn(UNIT_WAIT_KEY, evaluator.SELECTION_KEYS)


class TheDepthRulesCountAcrossAnAdoption(GymCase):
    def family_with_a_short_validation(self) -> None:
        self.holder("a")
        self.train_run("a", "train-a")
        self.store.set_state("a", **{WORKED_CYCLES_KEY: 7, VALIDATED_CYCLES_KEY: 3},
                             validation_version=1, validation_line={"passed": False, "checks": {
                                 "trades": True, "days": True, "mean": False, "t": False, "dsr": False, "quarters": False,
                                 "stress": True, "status": True}})

    def test_the_worked_cycles_survive_an_adoption_and_a_stale_mark_retires_nobody(self):
        self.family_with_a_short_validation()
        fam = self.store.family("a")
        self.assertEqual((worked_cycles(fam), short_left(fam, self.settings)), (7, 6), "four of the ten cycles are spent")
        self.assertNotIn(WORKED_CYCLES_KEY, evaluator.SELECTION_KEYS, "a count of the family's turns, like `cycles`")
        self.assertNotIn(VALIDATED_CYCLES_KEY, evaluator.SELECTION_KEYS)
        # League/live alone: the Gym's selection stands, and so do the validation, its mark and the count.
        self.new_live()
        fam = self.store.family("a")
        self.assertEqual((worked_cycles(fam), fam["state"][VALIDATED_CYCLES_KEY], short_left(fam, self.settings)), (7, 3, 6))
        # A new Gym: the validation is cleared with the selection; the turns the researcher worked are still its turns,
        # and the mark of a validation that no longer stands counts nothing down, however many cycles follow.
        self.new_gym()
        self.store.set_state("a", **{WORKED_CYCLES_KEY: 40})
        fam = self.store.family("a")
        self.assertEqual((worked_cycles(fam), fam["state"].get("validation_line")), (40, None))
        self.assertEqual((short_dead(fam, self.settings), short_left(fam, self.settings)), (None, None))


class NoIncubatorReviewWhileTheUnitWaits(GateCase):
    def test_a_version_that_met_the_line_and_waits_for_its_unit_is_paid_no_review_of_any_kind(self):
        """`incubator.due_reviews`: the incubator pays its own review for a practising version the gate is not reading.
        A version that waits before the gate for its unit is read by nobody and by design: the incubator's reader gives
        a family whose version met the line no row, so a review of it would buy nothing."""
        self.settings["gate"]["look_holds"] = None
        n = self.family("a")
        self.train("a", n, drift=drift_block(t=2.0, alpha_usd=150.0, drift_usd=20.0))
        self.robust("a", n)
        self.cohort("a", n)
        self.practised("a", n, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])
        incubator.facts(self.store, self.settings, self.root, clock=self.clock)
        sha = G.run_sha(self.store.version("a", n))
        self.store.set_state("a", gate_ready=False, validation_version=n, validation_image=None, validation_bundle=None,
                             validation_line={"passed": True}, **{UNIT_WAIT_KEY: {"version": n, "limit": 100.0}})
        self.assertEqual(incubator.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        self.assertFalse(incubator.reviewable(self.store, "a", n, sha))
        self.answer = strong
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual(((out.get("incubator") or {}).get("reviewed", []), len(self.sail.bodies) + len(self.asked)), ([], 0))
        # The control: the same version with no wait (and no place at the gate) is due the incubator's review.
        self.store.set_state("a", **{UNIT_WAIT_KEY: None})
        self.assertEqual([r["version"] for r in incubator.due_reviews(self.store, self.settings, self.root, clock=self.clock)], [n])
        self.assertTrue(incubator.reviewable(self.store, "a", n, sha))


if __name__ == "__main__":
    unittest.main()

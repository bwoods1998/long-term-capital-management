"""F1's research stream, part 2 (Oct 3, 2026): GATE-READY AT TRAIN and the cheap waste, each rule on the real `SwarmStore`.

On the store of that day more than half of the validated versions risked more a contract than a first real-money
position may, and the long-delta versions whose Train profit was mostly the market's drift made most of the Validation
hits, which the gate holds. The swarm learned both after the validation, the review, the audit or the look was paid
for. These tests pin what F1 changes:

- THE DRIFT CARRIER: a version the gate would hold a look at is set aside before it is validated, by the gate's own
  rule (the two are compared on every shape of fit), and one with no fit yet waits;
- THE UNIT: a version whose median one-lot unit on Train is over `researcher.max_unit_train_usd` (the Probe's floor
  less a margin) is set aside, and returns by itself when the limit moves;
- THE UNIT ON VALIDATION: a version that meets the line with a Validation unit over `researcher.max_unit_usd` (the
  money table's own fit), or with none its run states, waits before the gate (no review, no audit, no look) and goes
  on when the limit moves;
- a set-aside is never a failure mark, never touches a version at the gate, and files an idle death as no finding;
- THE STATUS: the best version's drift share and lean, its unit beside the limits, and its Train Sharpe beside the
  most the gate's power hold can ask, computed from the gate's own function and the COUNT of looks, never from what
  a look found; both follow the gate (off while it makes no sealed look);
- THE PROGRAM IN SIGHT: a researcher is shown its program whenever its history no longer holds it; a fork or a
  revival is handed its parent's;
- THE ZERO-TRADE PROBE over all the family's roots, and the settings as code;
- the contract's and the architect's lines on what reaches real money.

Synthetic families, programs and figures only."""

from __future__ import annotations

import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

from league.live import money
from league.swarm import evidence
from league.swarm import settings as S
from league.swarm.architect import SYSTEM, Architect, tag_of
from league.swarm.gate import HOLD_POWER_STAGE, Gate, holdout_sessions, look_hold_settings
from league.swarm.researcher import (CONTRACT, MAX_UNIT_TRAIN_USD, MAX_UNIT_USD, PROGRAM_HEAD, SET_ASIDE_KEY, UNIT_WAIT_KEY,
                                     Researcher, awaiting_validation, carrier_share, drift_held, gate_looks, idle_cause,
                                     idle_dead, in_sight, max_unit, max_unit_train, power_bar, screen_best, set_aside,
                                     train_gate, train_record, train_row, version_unit)
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_swarm_drift import train_result
from league.tests.test_swarm_look_holds import STRONG_SHARPE, HoldCase, lean
from league.tests.test_swarm_researcher import ResearcherCase, calls_in
from league.tests.test_swarm_rounds import RoundCase
from league.tests.test_swarm_sweep import SweepCase, scored

LIGHT = dict(alpha=150.0, drift=20.0, beta=200.0)     # long delta, drift share 0.118: not a carrier
CARRIER = dict(alpha=100.0, drift=60.0, beta=200.0)   # long delta, drift share 0.375: the gate holds its look
SHORT = dict(alpha=100.0, drift=60.0, beta=-200.0)    # the same share, short delta: never held for drift
PROGRAM = "# {tag}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{'width': 5}}\ndef decide(ctx):\n    return []  # {tag}\n"


def looks_on(case: unittest.TestCase) -> None:
    """The gate makes the sealed look for this test (`gate.SEALED_LOOKS`: RoundCase switches it on too): the carrier
    screen and the printed bar mirror that look's holds and are off without it."""
    switch = patch("league.swarm.gate.SEALED_LOOKS", True)
    switch.start()
    case.addCleanup(switch.stop)


def train(name: str, *, drift: dict | None = LIGHT, unit: float | None = 60.0, sharpe: float = 0.06, **kw) -> dict:
    """An invented eligible Train result: its drift fit (`drift` None: a run with no fit), the Gym's median one-lot
    unit (None: a run without the figure) and its all-days daily Sharpe."""
    r = train_result(name, drift=None if drift is None else lean(**drift), sharpe_daily=sharpe, **kw)
    if unit is not None:
        r["summary"]["median_max_loss_per_structure"] = unit
    return r


class GateReadyCase(RoundCase):
    """The tournament's case with the gate's holds at their defaults and the drift screen on (RoundCase: both off)."""

    def setUp(self):
        super().setUp()
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}
        self.settings["tournament"]["drift_screen"] = True

    def version(self, fid: str, tag: str, *, score: float | None = 2.0, **kw) -> tuple[int, str]:
        """A new version of `fid` with one Train run (`train`), a candidate at `score` (None: not a candidate)."""
        if self.store.family(fid) is None:
            self.store.add_family({"id": fid, "mechanism": f"An invented mechanism for {fid}, a gate-ready test family.",
                                   "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 2]}, origin="seed")
        v = self.store.add_version(fid, PROGRAM.format(tag=f"{fid} {tag}"), {}, author="seed")
        n = int(v["n"])
        row = self.store.add_run(fid, n, {**train(f"{fid}-{tag}", **kw)}, window="train", stress=1.0, purpose="train")
        run = self.store.run(row["run_id"])
        self.store._exec("UPDATE runs SET summary=? WHERE run_id=?", (json.dumps({**run["summary"], "train_score": score,
                                                                                  "train_eligible": score is not None}), row["run_id"]))
        if score is not None:
            fam = self.store.family(fid)
            state = fam["state"]
            rows = sorted([*(state.get("train_candidates") or []), [score, n, row["run_id"]]], key=lambda c: -c[0])
            values = {"train_candidates": rows}
            if fam["best_train"] is None or score > fam["best_train"]:
                self.store.update_family(fid, best_train=score)
                values.update(best_train_version=n, best_train_run=row["run_id"])
            self.store.set_state(fid, **values)
        return n, row["run_id"]

    def best(self, fid: str) -> tuple:
        fam = self.store.family(fid)
        return fam["best_version"], fam["state"].get("best_train_version"), fam["best_train"]

    def robustness_events(self, fid: str) -> list[tuple]:
        return [(e["payload"]["action"], e["payload"]["version"], e["payload"]["next"]) for e in self.store.events_after(0)
                if e["kind"] == "swarm.robustness" and e["family"] == fid]


# ------------------------------------------------------------------------------------------------ 1. the drift carrier
class TheDriftCarrier(GateReadyCase):
    def test_a_carrier_is_set_aside_and_the_next_candidate_takes_its_place(self):
        one, run = self.version("a", "one", score=3.0, drift=CARRIER)
        two, _ = self.version("a", "two", score=2.0, drift=LIGHT)
        self.assertEqual(self.best("a"), (None, one, 3.0))
        rows = screen_best(self.store, "a", self.settings)
        self.assertEqual([(r["version"], r["kind"], r["action"], r["next"]) for r in rows], [(one, "drift", "set_aside", two)])
        self.assertEqual(self.best("a"), (None, two, 2.0), "the next candidate is the best")
        state = self.store.family("a")["state"]
        self.assertEqual([c[1] for c in state["train_candidates"]], [two])
        self.assertFalse(state.get("robust_failed"), "set aside, never marked failed")
        self.assertFalse(state.get("drift_failed"), "nor failed by the drift screen: its alpha passed that")
        mark = state[SET_ASIDE_KEY][str(one)]
        self.assertEqual((mark["kind"], mark["run"], mark["under"]), ("drift", run, [0.25, 80.0]))
        self.assertEqual(mark["why"], "is a drift carrier by the gate's rule (long delta, 38% of its Train profit the market's drift)")
        self.assertNotIn("0.25", mark["why"], "the gate's line is not printed beside the share")
        self.assertEqual(self.robustness_events("a"), [("set_aside", one, two)])
        self.assertEqual(screen_best(self.store, "a", self.settings), [], "nothing more: the new best is ready")

    def test_the_tournament_validates_the_next_candidate_and_never_the_carrier(self):
        one, _ = self.version("a", "one", score=3.0, drift=CARRIER)
        two, _ = self.version("a", "two", score=2.0, drift=LIGHT)
        self.version("solo", "one", score=3.0, drift=CARRIER)
        self.version("short", "one", score=3.0, drift=SHORT)
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual(sorted((j.family, j.version) for j in self.pool.jobs), [("a", two), ("short", 1)],
                         "no validation is bought for a version the gate would hold")
        self.assertEqual((out["set_aside"], out["failed_drift"]), (["a", "solo"], []), "a set-aside is no drift-screen failure")
        self.assertEqual(self.best("solo"), (None, None, None), "a family left with none has no eligible Train version")
        self.assertFalse(awaiting_validation(self.store.family("solo")), "so it awaits nothing")

    def test_the_screen_and_the_gates_hold_never_disagree(self):
        """The screen is the gate's own rule read one window earlier: on every shape of fit, at every setting of the
        share, a version is held back here exactly when `Gate.look_hold` would hold its look for drift."""
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        blocks = {"no fit": None}
        for alpha in (-80.0, 0.0, 30.0, 75.0, 100.0, 300.0):
            for drift in (-60.0, 0.0, 25.0, 60.0, 100.0):
                for beta in (-200.0, 0.0, 200.0):
                    blocks[f"a{alpha} d{drift} b{beta}"] = lean(alpha, drift, beta)
        broken = lean(100.0, 60.0, 200.0)
        del broken["pooled"]["beta"]
        blocks["no beta"] = broken
        self.settings["researcher"]["max_unit_train_usd"] = None  # the drift rule alone
        seen = set()
        for name, block in blocks.items():
            fid = f"f{len(seen)}"
            seen.add(fid)
            self.store.add_family({"id": fid, "mechanism": f"An invented mechanism, fit {name}.", "structure": "debit_vertical",
                                   "roots": ["SPY"]}, origin="seed")
            v = self.store.add_version(fid, PROGRAM.format(tag=fid), {}, author="seed")
            r = train_result(fid, drift=None if block is None else block)
            self.store.add_run(fid, v["n"], r, window="train", stress=1.0, purpose="train")
            fam = self.store.family(fid)
            for share in (0.25, 0.10, 0.60, 0.0, 1.0):
                self.settings["gate"]["look_holds"] = {"drift_share": share, "min_power": None}
                hold = gate.look_hold(fam, v["n"])
                mine = train_gate(self.store, fam, v["n"], self.settings)
                self.assertEqual(not mine["ready"], hold is not None, (name, share, mine, hold))
                if hold is not None:
                    self.assertIn(mine["kind"], ("fit", "drift"))
                    self.assertEqual(mine["kind"] == "fit", block is None, "only a version with no fit at all waits")
        self.assertEqual(carrier_share(self.settings), look_hold_settings(self.settings)[0], "one reading of one setting")
        exact = evidence.drift_lean(evidence.drift_numbers(lean(75.0, 25.0, 200.0)))
        self.assertEqual((exact["share"], drift_held(exact, 0.25)), (0.25, True), "at the line is held, as at the gate")

    def test_a_version_with_no_fit_waits_and_is_not_set_aside(self):
        self.settings["tournament"]["drift_screen"] = False  # the gate's rule alone asks for the fit
        n, _ = self.version("a", "one", score=3.0, drift=None)
        fam = self.store.family("a")
        self.assertEqual((train_gate(self.store, fam, n, self.settings)["kind"], screen_best(self.store, "a", self.settings)),
                         ("fit", []))
        self.assertEqual(self.best("a"), (None, n, 3.0), "it stays the best")
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual((self.pool.jobs, out["waiting_gate_ready"]), ([], ["a"]), "not validated until its fit is made")
        me = Researcher(self.store, self.router, self.pool, self.settings, contract="C", clock=self.clock)
        self.assertEqual(me.robust_labels(fam, n), ("stress_1.5", "mid", "drift"), "its Train run is made again for the fit")
        self.store.set_state("a", robustness={str(n): {"drift": {"status": "ok", **evidence.drift_numbers(lean(**LIGHT))}}})
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual([(j.family, j.version) for j in self.pool.jobs], [("a", n)], "the fit landed and it is not a carrier")

    def test_a_version_waiting_at_the_gate_is_left_to_the_gate(self):
        n, _ = self.version("a", "one", score=3.0, drift=CARRIER, unit=400.0)
        self.store.update_family("a", best_version=n, validated_version=n)
        self.store.set_state("a", validation_version=n, gate_ready=True, validation_line={"passed": True})
        self.assertEqual(screen_best(self.store, "a", self.settings), [], "the gate holds it by its own rule and keeps its record")
        self.assertEqual(self.best("a"), (n, n, 3.0))
        self.store.set_state("a", gate_ready=False)  # the gate is done with it
        self.assertEqual([r["version"] for r in screen_best(self.store, "a", self.settings)], [n])
        state = self.store.family("a")["state"]
        self.assertEqual((state["validation_version"], state.get("gate_outcome")), (n, None), "nothing at the gate is touched")

    def test_the_switches(self):
        n, _ = self.version("a", "one", score=3.0, drift=CARRIER)
        fam = self.store.family("a")
        for change in ({"researcher": {"carrier_screen": False}}, {"gate": {"look_holds": None}},
                       {"gate": {"look_holds": {"drift_share": None, "min_power": 0.3}}}):
            settings = copy.deepcopy(self.settings)
            for block, values in change.items():
                settings[block].update(values)
            self.assertIsNone(carrier_share(settings), change)
            self.assertTrue(train_gate(self.store, fam, n, settings)["ready"], change)
            self.assertEqual(screen_best(self.store, "a", settings), [], change)
        for bad in ("off", 0, None, "false"):
            self.assertEqual(carrier_share({**self.settings, "researcher": {"carrier_screen": bad}}), 0.25, bad)

    def test_the_screen_follows_the_gate_and_is_off_while_it_makes_no_sealed_look(self):
        """The drift hold is a hold on the sealed look. In a tree whose gate makes none, nothing is set aside as a
        carrier and no researcher is told of a rule that does not run."""
        n, _ = self.version("a", "one", score=3.0, drift=CARRIER)
        fam = self.store.family("a")
        self.assertTrue(gate_looks())
        self.assertFalse(train_gate(self.store, fam, n, self.settings)["ready"])
        with patch("league.swarm.gate.SEALED_LOOKS", False):
            self.assertFalse(gate_looks())
            self.assertIsNone(carrier_share(self.settings))
            self.assertTrue(train_gate(self.store, fam, n, self.settings)["ready"])
            self.assertEqual(screen_best(self.store, "a", self.settings), [])
            self.assertIsNone(power_bar(self.store, self.settings))
            me = Researcher(self.store, self.router, self.pool, self.settings, contract="C", clock=self.clock)
            text = me.gate_text(fam)
            self.assertNotIn("drift carrier", text)
            self.assertNotIn("Sharpe", text)
            self.assertIn("its median one-lot unit on Train", text, "the unit is the money table's, whatever the gate does")


# ---------------------------------------------------------------------------------------------------------- 2. the unit
class TheUnit(GateReadyCase):
    def test_a_unit_over_the_limit_is_set_aside_and_returns_when_the_limit_moves(self):
        big, run = self.version("a", "big", score=3.0, unit=140.0)
        small, _ = self.version("a", "small", score=2.0, unit=80.0)
        rows = screen_best(self.store, "a", self.settings)
        self.assertEqual([(r["version"], r["kind"], r["next"]) for r in rows], [(big, "unit", small)])
        mark = self.store.family("a")["state"][SET_ASIDE_KEY][str(big)]
        self.assertEqual(mark["why"], "risks $140.00 a contract at its median on Train, over the $80.00 a version may risk "
                                      "there to be validated")
        self.assertEqual(mark["under"], [0.25, 80.0], "the Train limit, not the Probe's floor")
        self.assertEqual(self.best("a"), (None, small, 2.0), "at the limit is within it")
        self.assertFalse(self.store.family("a")["state"].get("robust_failed"), "a size is no finding against the program")
        self.settings["researcher"]["max_unit_train_usd"] = 150  # the account grew: the Probe's cap is above the floor now
        self.assertEqual(screen_best(self.store, "a", self.settings), [])
        state = self.store.family("a")["state"]
        self.assertEqual((self.best("a"), state[SET_ASIDE_KEY]), ((None, big, 3.0), {}), "it has its place back, by itself")
        self.assertEqual([c[1] for c in state["train_candidates"]], [big, small])
        self.assertEqual(state["best_train_run"], run)
        self.assertEqual(self.robustness_events("a"), [("set_aside", big, small), ("restored", big, None)])
        self.settings["researcher"]["max_unit_train_usd"] = 100
        self.assertEqual([(r["version"], r["next"]) for r in screen_best(self.store, "a", self.settings)], [(big, small)],
                         "and it is set aside again when the limit comes back down")
        self.settings["researcher"]["max_unit_usd"] = 500  # the Validation limit is another setting: it moves nothing here
        self.assertEqual(screen_best(self.store, "a", self.settings), [])
        self.assertEqual(self.best("a"), (None, small, 2.0))

    def test_the_validation_limit_is_the_money_tables_own_fit_and_the_train_limit_sits_under_it(self):
        """R1. `researcher.max_unit_usd` defaults to the constitution's Probe floor, and THE UNIT ON VALIDATION holds a
        unit back exactly when `money.fits_probe` refuses it for an account whose 5% share is under the floor: that is
        the run the money table reads. The Train screen is a cheap first filter with a margin under it (80): the
        Validation unit is the larger in three runs of four, so a Train unit between the two is stopped."""
        table = money.Table.from_constitution()
        self.assertEqual(Decimal(str(MAX_UNIT_USD)), table.probe_floor, "the default is the Probe's one-contract floor")
        self.assertEqual((max_unit(S.DEFAULTS), max_unit_train(S.DEFAULTS)), (MAX_UNIT_USD, MAX_UNIT_TRAIN_USD))
        self.assertEqual(MAX_UNIT_TRAIN_USD, 80.0)
        self.assertLess(MAX_UNIT_TRAIN_USD, MAX_UNIT_USD)
        equity = table.probe_floor  # a small account: its share of equity is below the floor, so the floor decides
        self.assertLess(money.probe_cap(table, equity), table.probe_floor)
        tournament = Tournament(self.store, self.pool, self.settings)
        for i, unit in enumerate((0.01, 31.0, 79.99, 80.0, 80.01, 99.99, 100.0, 100.01, 145.5, 559.0)):
            self.assertEqual(not tournament.unit_over(unit), money.fits_probe(table, equity, Decimal(str(unit))), unit)
            n, _ = self.version(f"u{i}", "one", score=2.0, unit=unit)
            ready = train_gate(self.store, self.store.family(f"u{i}"), n, self.settings)
            self.assertEqual((ready["ready"], ready["unit"], ready["limit"]), (unit <= 80.0, unit, 80.0), unit)
        self.assertTrue(tournament.unit_over(None), "a unit the run does not state fits no Probe: the money table says unknown")

    def test_the_unit_is_the_gyms_own_figure_of_the_versions_train_run(self):
        n, run = self.version("a", "one", score=2.0, unit=64.5)
        fam = self.store.family("a")
        self.assertEqual((version_unit(self.store, fam, n), train_row(self.store, fam, n)["run_id"]), (64.5, run))
        self.store.add_run("a", n, train("hot", unit=900.0), window="train", stress=1.5, purpose="robustness")
        self.store.add_run("a", n, train("mid", unit=900.0), window="train", stress=0.0, purpose="robustness")
        self.assertEqual(version_unit(self.store, fam, n), 64.5, "never a robustness run's")
        bare, _ = self.version("a", "bare", score=1.0, unit=None)
        self.assertIsNone(version_unit(self.store, self.store.family("a"), bare))
        self.assertTrue(train_gate(self.store, self.store.family("a"), bare, self.settings)["ready"],
                        "a run without the figure is not set aside for it")

    def test_null_turns_it_off_and_a_misread_value_keeps_the_brake(self):
        n, _ = self.version("a", "one", score=3.0, unit=400.0)
        fam = self.store.family("a")
        self.settings["researcher"]["max_unit_usd"] = None
        self.assertIsNone(max_unit(self.settings))
        self.assertFalse(train_gate(self.store, fam, n, self.settings)["ready"], "the Train screen has its own setting")
        self.settings["researcher"]["max_unit_train_usd"] = None
        self.assertIsNone(max_unit_train(self.settings))
        self.assertTrue(train_gate(self.store, fam, n, self.settings)["ready"])
        for bad in ("big", True, False, 0, -5, float("nan"), float("inf"), [100]):
            self.settings["researcher"].update(max_unit_usd=bad, max_unit_train_usd=bad)
            self.assertEqual((max_unit(self.settings), max_unit_train(self.settings)), (MAX_UNIT_USD, MAX_UNIT_TRAIN_USD), bad)
        self.assertEqual((max_unit({}), max_unit_train({})), (MAX_UNIT_USD, MAX_UNIT_TRAIN_USD))

    def test_a_mark_under_another_evaluator_or_of_a_demoted_version_is_dropped(self):
        big, _ = self.version("a", "big", score=3.0, unit=140.0)
        screen_best(self.store, "a", self.settings)
        state = self.store.family("a")["state"]
        self.store.set_state("a", **{SET_ASIDE_KEY: {str(big): {**state[SET_ASIDE_KEY][str(big)], "evaluator": {"image": "old"}}}})
        self.assertEqual(set_aside(self.store.family("a"), None), set_aside(self.store.family("a")))
        self.assertEqual(set_aside(self.store.family("a"), {"image": "new"}), {})
        screen_best(self.store, "a", self.settings)
        self.assertEqual(self.store.family("a")["state"][SET_ASIDE_KEY], {}, "another Gym's mark says nothing of this one's runs")
        self.assertEqual(self.best("a"), (None, None, None), "and it gives no place back")


class TheUnitOnValidation(RoundCase):
    """The money table fits the Probe to the VALIDATION run's unit. A version that met the line with that unit over
    the limit waits before the gate: nothing is paid for it there, and it goes on by itself when the limit moves."""

    def setUp(self):
        super().setUp()
        self.unit = 140.0
        self.answer = self.gym

    def gym(self, job):
        from league.tests.test_swarm_rounds import strong

        out = strong(job)
        if job.window == "validation":
            out["summary"]["median_max_loss_per_structure"] = self.unit
        return out

    def test_a_line_pass_over_the_unit_waits_before_the_gate_and_goes_on_when_the_limit_moves(self):
        self.family("a")
        tournament = Tournament(self.store, self.pool, self.settings)
        out = tournament.validate(self.store.families(alive=True))
        self.assertEqual((out["judged"]["a"]["passed"], out["judged"]["a"]["unit_wait"]), (True, True))
        fam = self.store.family("a")
        state = fam["state"]
        self.assertEqual((state["validation_line"]["passed"], state["gate_ready"], state["typical_max_loss_usd"]), (True, False, 140.0))
        self.assertEqual(state[UNIT_WAIT_KEY], {"version": 1, "limit": 100.0})
        self.assertEqual((fam["validations"], fam["validated_version"]), (1, 1), "validated like any version: only the gate waits")
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual((gate["looked"], gate["refused"], gate["look_held"]), ([], [], []))
        self.assertEqual((self.sail.bodies, self.asked, self.store.looks(), self.store.refusals("a"), self.store.look_holds("a")),
                         ([], [], [], [], []), "no review, no audit, no look, and no verdict against it: a wait, never a bar")
        self.assertEqual([j.window for j in self.pool.jobs], ["validation"])
        status = Researcher(self.store, self.router, self.pool, self.settings, contract="C", clock=self.clock).status(fam)
        self.assertIn("Validation of version 1: it met the validation line", status)
        self.assertIn("It waits before the gate: over the Validation year one structure of it risks more than a first "
                      "real-money position may", status)
        self.assertNotIn("140", status, "D2a: no figure Validation measured")
        tournament.validate(self.store.families(alive=True))
        self.assertFalse(self.store.family("a")["state"]["gate_ready"], "still over: it waits")
        self.settings["researcher"]["max_unit_usd"] = 150  # the account grew
        again = tournament.validate(self.store.families(alive=True))
        state = self.store.family("a")["state"]
        self.assertEqual((again["queued"], state["gate_ready"], state[UNIT_WAIT_KEY]), (0, True, None), "no new validation run")
        self.assertNotIn("It waits before the gate", Researcher(self.store, self.router, self.pool, self.settings, contract="C",
                                                                 clock=self.clock).status(self.store.family("a")))

    def test_a_line_pass_whose_validation_run_states_no_unit_waits_too(self):
        """The money table keeps a version with no known unit a Candidate, so the gate's spend on it buys no Probe."""
        from league.tests.test_swarm_rounds import strong

        def no_unit(job):
            out = strong(job)
            out["summary"].pop("median_max_loss_per_structure", None)
            out["summary"].pop("max_loss_opened", None)
            return out
        self.answer = no_unit
        self.family("a")
        tournament = Tournament(self.store, self.pool, self.settings)
        out = tournament.validate(self.store.families(alive=True))
        state = self.store.family("a")["state"]
        self.assertEqual((out["judged"]["a"]["passed"], state["typical_max_loss_usd"]), (True, None))
        self.assertEqual((state["gate_ready"], state[UNIT_WAIT_KEY]), (False, {"version": 1, "limit": 100.0, "unknown": True}))
        status = Researcher(self.store, self.router, self.pool, self.settings, contract="C", clock=self.clock).status(
            self.store.family("a"))
        self.assertIn("It waits before the gate: its Validation run states no unit for one structure of it", status)
        tournament.validate(self.store.families(alive=True))
        self.assertFalse(self.store.family("a")["state"]["gate_ready"], "an unknown unit stays unknown: it waits")

    def test_a_unit_within_the_limit_a_failed_line_or_the_screen_off_never_waits(self):
        self.unit = 100.0
        self.family("fits")
        self.family("weak")
        from league.tests.test_swarm_rounds import weak

        def answer(job):
            out = weak(job) if job.family == "weak" else self.gym(job)
            out["summary"]["median_max_loss_per_structure"] = 400.0 if job.family in ("weak", "off") else self.unit
            return out
        self.answer = answer
        tournament = Tournament(self.store, self.pool, self.settings)
        tournament.validate(self.store.families(alive=True))
        fits, failed = self.store.family("fits")["state"], self.store.family("weak")["state"]
        self.assertEqual((fits["gate_ready"], fits[UNIT_WAIT_KEY]), (True, None), "at the limit fits, as the money table's fit")
        self.assertEqual((failed["validation_line"]["passed"], failed["gate_ready"], failed[UNIT_WAIT_KEY]), (False, False, None))
        self.settings["researcher"]["max_unit_usd"] = None
        self.family("off")
        tournament.validate(self.store.families(alive=True))
        off = self.store.family("off")["state"]
        self.assertEqual((off["gate_ready"], off[UNIT_WAIT_KEY]), (True, None), "null: no unit screen at all")


# --------------------------------------------------------------------------------------------- 3. the idle rule's verdict
class TheVerdict(GateReadyCase):
    def test_a_family_whose_versions_were_all_set_aside_is_filed_by_what_set_them_aside(self):
        self.version("sized", "one", score=3.0, unit=300.0)
        self.version("carrier", "one", score=3.0, drift=CARRIER)
        for fid in ("sized", "carrier"):
            screen_best(self.store, fid, self.settings)
            self.store.update_family(fid, trials=600, since_val_trials=600)
            self.assertIn("no eligible Train version", idle_dead(self.store.family(fid), self.settings))
        self.assertEqual(train_record(self.store, self.store.family("sized")), {"screen": "unit", "eligible": True})
        self.assertEqual(train_record(self.store, self.store.family("carrier")), {"screen": "carrier", "eligible": True})
        self.assertIn("a limit on size, not evidence of an unprofitable mechanism", idle_cause("unit"))
        self.assertIn("set aside, not refuted: this is not evidence of an unprofitable mechanism", idle_cause("carrier"))
        # A version the DRIFT SCREEN demoted is the drift finding, as ever: the screen's own mark, not a set-aside.
        self.version("failed", "one", score=3.0, drift=LIGHT)
        self.store.update_family("failed", best_train=None, trials=600, since_val_trials=600)
        self.store.set_state("failed", best_train_version=None, train_candidates=[], robust_failed=[1],
                             drift_failed={"1": "t 0.4"})
        self.assertEqual(train_record(self.store, self.store.family("failed"))["screen"], "drift")
        retired = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(sorted(r["family"] for r in retired), ["carrier", "failed", "sized"])
        tags = {g["family"]: tag_of(g, self.store.family(g["family"])) for g in self.store.graveyard(limit=5)}
        self.assertEqual(tags, {"sized": "UNRESOLVED", "carrier": "UNRESOLVED", "failed": "DRIFT"},
                         "a set-aside, for size or as a carrier, is no mechanism verdict (it closes no cell: the researcher "
                         "was told 'no finding against the program', and such a version had passed the drift screen); "
                         "only the drift screen's own failure is the drift finding")
        from league.swarm import cards
        self.assertNotIn("UNRESOLVED", cards.MECHANISM_VERDICTS)
        self.assertIn("DRIFT", cards.MECHANISM_VERDICTS)


# ---------------------------------------------------------------------------------------- 4. the researcher's own runs
class TheResearcher(ResearcherCase):
    def setUp(self):
        super().setUp()
        looks_on(self)
        self.fid = self.fam["id"]
        self.drift, self.unit = LIGHT, 60.0
        self.pool.answer = lambda job: train(job.name, drift=self.drift, unit=self.unit, roots=job.roots)

    def run_(self, code: str | None = None, **args):
        out: dict = {"tool_calls": 0}
        me = self.researcher()
        view = me._gym_run(self.store.family(self.fid), {"code": code or self.code, **args}, out, author="synthetic")
        return me, view, out

    def test_a_run_that_is_a_carrier_or_over_the_unit_is_not_the_best_and_says_why(self):
        self.drift = CARRIER
        me, view, out = self.run_()
        self.assertEqual((view["train_score"]["eligible"], out["score"]), (False, None))
        self.assertEqual(view["train_score"]["why_not_eligible"], "this version is a drift carrier by the gate's rule (long "
                         "delta, 38% of its Train profit the market's drift), so it is not validated")
        fam = self.store.family(self.fid)
        self.assertEqual((fam["best_train"], fam["state"].get("train_candidates") or [], self.pool.jobs[1:]), (None, [], []),
                         "no candidate, no best, and no robustness run for it")
        self.assertEqual(list(fam["state"][SET_ASIDE_KEY]), ["1"])
        answer = me._local_tool(fam, "submit", {"run_id": view["run_id"]}, {})
        self.assertEqual(answer, {"error": "that run cannot be your best: its version is a drift carrier by the gate's rule (long "
                                           "delta, 38% of its Train profit the market's drift), so it is not validated"})
        self.drift, self.unit = LIGHT, 250.0
        me, view, out = self.run_(self.code + "\n# wider\n")
        self.assertIn("risks $250.00 a contract at its median on Train", view["train_score"]["why_not_eligible"])
        self.unit = 80.0
        me, view, out = self.run_(self.code + "\n# narrower\n")
        self.assertEqual((view["train_score"]["eligible"], self.store.family(self.fid)["state"]["best_train_version"]), (True, 3))
        status = me.status(self.store.family(self.fid))
        self.assertIn("Set aside, not validated while this stands", status)
        self.assertIn("version 2 risks $250.00 a contract", status)
        self.assertIn("version 1 is a drift carrier by the gate's rule", status)

    def test_a_run_of_a_version_already_at_the_gate_sets_nothing_aside(self):
        """`gate_blocks` on the researcher's own path: a version waiting at the gate is the gate's (it holds the look by
        its own rule and keeps its own record), so a Train run of it read again never takes its place away."""
        self.drift = CARRIER
        me = self.researcher()
        n = int(self.store.add_version(self.fid, self.code, {}, author="synthetic")["n"])
        self.store.add_run(self.fid, n, train("at-the-gate", drift=CARRIER), window="train", stress=1.0, purpose="train")
        self.store.update_family(self.fid, best_version=n, validated_version=n)
        self.store.set_state(self.fid, validation_version=n, gate_ready=True, validation_line={"passed": True})
        self.assertFalse(train_gate(self.store, self.store.family(self.fid), n, self.settings)["ready"], "a carrier")
        self.assertIsNone(me.gate_blocks(self.fid, n))
        fam = self.store.family(self.fid)
        self.assertEqual((fam["best_version"], fam["state"].get(SET_ASIDE_KEY)), (n, None), "left to the gate")
        self.store.set_state(self.fid, gate_ready=False)  # the gate is done with it
        self.assertIn("is a drift carrier by the gate's rule", me.gate_blocks(self.fid, n))
        fam = self.store.family(self.fid)
        self.assertEqual((fam["best_version"], list(fam["state"][SET_ASIDE_KEY])), (None, [str(n)]))

    def test_a_stored_result_read_again_changes_nothing(self):
        self.unit = 250.0
        me, view, out = self.run_()
        before = self.store.family(self.fid)["state"]
        again, out = me._gym_run(self.store.family(self.fid), {"code": self.code}, {"tool_calls": 0}, author="synthetic"), None
        self.assertEqual(again["already_run"], "the stored result")
        self.assertEqual(again["train_score"]["why_not_eligible"], view["train_score"]["why_not_eligible"])
        self.assertEqual(self.store.family(self.fid)["state"], before)


class TheSweep(SweepCase):
    def test_a_sweeps_rows_are_screened_one_by_one(self):
        def answer(job):
            r = scored(job)
            r["drift"] = lean(**(CARRIER if job.params.get("vrp_min") == 1.4 else LIGHT))
            r["summary"]["median_max_loss_per_structure"] = 300.0 if job.params.get("vrp_min") == 1.5 else 70.0
            return r
        looks_on(self)
        self.pool = type(self.pool)(answer)
        self.first()
        view, out = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.4}, {"vrp_min": 1.5}])
        rows = {r["params"]["vrp_min"]: r for r in view["table"]}
        self.assertEqual({k: r["eligible"] for k, r in rows.items()}, {1.3: True, 1.4: False, 1.5: False})
        self.assertIn("is a drift carrier by the gate's rule", rows[1.4]["why_not"])
        self.assertIn("risks $300.00 a contract", rows[1.5]["why_not"])
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["best_train_version"], rows[1.3]["version"], "the best is the row the gate would take")
        self.assertEqual(sorted(m["kind"] for m in fam["state"][SET_ASIDE_KEY].values()), ["drift", "unit"])
        self.assertEqual(view["table"][0]["params"], {"vrp_min": 1.3}, "and it heads the table")


# ------------------------------------------------------------------------------------------------------ 5. the status
class TheStatus(HoldCase):
    def setUp(self):
        super().setUp()
        self.settings["researcher"]["carrier_screen"] = True  # HoldCase tests the gate's hold alone; here both are on
        self.settings["tournament"]["drift_screen"] = True

    def me(self) -> Researcher:
        return Researcher(self.store, self.router, self.pool, self.settings, contract="C", clock=self.clock)

    def family_with(self, fid: str, **kw) -> int:
        self.family(fid)
        row = self.store.add_run(fid, 1, train(fid, **kw), window="train", stress=1.0, purpose="train")
        self.store.set_state(fid, best_train_version=1, best_train_run=row["run_id"])
        return 1

    def test_the_best_versions_figures_stand_beside_what_the_gate_will_ask(self):
        self.family_with("a", drift=LIGHT, unit=64.0, sharpe=0.061)
        text = self.me().gate_text(self.store.family("a"))
        bar = power_bar(self.store, self.settings)["sharpe"]
        self.assertEqual(text, "What the gate will ask of version 1, on its Train figures: 12% of its Train profit is the "
                               "market's drift and it is long delta: not a drift carrier by the gate's rule (it holds a look at a "
                               "long-delta version whose profit is too much the market's drift); its median one-lot unit on Train "
                               "is $64.00; a version is validated while that is at most $80.00 (the Validation year's is usually "
                               "the larger, and a first real-money position may risk $100.00 a contract there); its all-days "
                               "daily Sharpe on Train is 0.061; the gate looks at a version whose all-days daily Sharpe over the "
                               f"Validation year reaches {bar:.3f} (the most it asks after the looks it has made so far, whatever "
                               "they found; every further look raises it).")
        self.assertIn(text, self.me().status(self.store.family("a")), "every cycle")
        self.assertNotIn("0.25", text, "the drift line is said in words, never as the number beside the share")
        self.family_with("s", drift=SHORT, unit=64.0)
        self.assertIn("38% of its Train profit is the market's drift and it is short or flat delta: not a drift carrier",
                      self.me().gate_text(self.store.family("s")))
        self.family_with("nofit", drift=None)
        self.settings["tournament"]["drift_screen"] = False
        self.assertIn("it has no Train drift fit yet, so it waits for one before it is validated",
                      self.me().gate_text(self.store.family("nofit")))

    def test_the_bar_is_the_gates_own_function_at_the_count_of_looks(self):
        """The Sharpe printed is where `evidence.holdout_power` crosses `gate.look_holds.min_power` at the strictest
        level the next look can face: with no look on record that is the gate's own bar (a validated version just above
        it is looked at, one just below is held for power), and it rises with each look MADE."""
        first = power_bar(self.store, self.settings)
        sessions = holdout_sessions()
        self.assertEqual((first["sessions"], first["min_power"], first["level"], first["looks"]),
                         (sessions, 0.30, evidence.HOLDOUT_ALPHA, 0))
        self.assertGreaterEqual(evidence.holdout_power(first["sharpe"], sessions, first["level"]), 0.30)
        self.assertLess(evidence.holdout_power(first["sharpe"] - 1e-6, sessions, first["level"]), 0.30)
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        above = self.ready("above", drift=LIGHT, sharpe=round(first["sharpe"] + 0.0006, 5))
        below = self.ready("below", drift=LIGHT, sharpe=round(first["sharpe"] - 0.0006, 5))
        self.assertIsNone(gate.look_hold(self.store.family("above"), above))
        self.assertEqual(gate.look_hold(self.store.family("below"), below)["holds"], [HOLD_POWER_STAGE])
        for i in range(3):  # three looks on record: the next can face a stricter level, so the bar rises
            self.store.add_look(f"looked{i}", 1, f"sha{i}", passed=False, p_value=0.8, detail={})
        later = power_bar(self.store, self.settings)
        self.assertEqual((later["looks"], later["level"]), (3, evidence.HOLDOUT_ALPHA / 4))
        self.assertEqual(later["level"], evidence.holm_level([0.8, 0.8, 0.8]), "with every look failed it is the gate's own level")
        self.assertGreater(later["sharpe"], first["sharpe"])
        self.assertIn(f"reaches {later['sharpe']:.3f} (the most it asks after the looks it has made so far, whatever they found",
                      self.me().gate_text(self.store.family("above")))
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.60}
        self.assertGreater(power_bar(self.store, self.settings)["sharpe"], later["sharpe"], "and with the hold's setting")
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": None}
        self.assertIsNone(power_bar(self.store, self.settings))
        self.assertNotIn("Sharpe", self.me().gate_text(self.store.family("above")), "no hold, no bar")

    def test_the_bar_never_tells_a_passed_look_from_a_failed_one(self):
        """The evidence rule: a prompt may know how many looks the gate made, and nothing any of them found. The figure
        a researcher reads is the same whether a look passed or failed, whatever its p-value, and a look in flight
        counts as one made; it is never under the gate's own bar, so a version that reaches it is looked at."""
        def bar_after(looks):
            for row in self.store._all("SELECT seq FROM looks"):
                self.store._exec("DELETE FROM looks WHERE seq=?", (row["seq"],))
            for i, (passed, p) in enumerate(looks):
                self.store.add_look(f"looked{i}", 1, f"sha{i}", passed=passed, p_value=p, detail={})
            return power_bar(self.store, self.settings)

        failed = [(False, 0.836), (False, 0.831), (False, 0.996)]
        base = bar_after(failed)
        fourth_failed = bar_after(failed + [(False, 0.9)])
        fourth_passed = bar_after(failed + [(True, 0.001)])
        unread = bar_after(failed + [(False, None)])  # a look whose p-value was never recorded is a look made all the same
        self.assertEqual(fourth_passed, fourth_failed, "one number whatever the look found")
        self.assertEqual(unread, fourth_failed)
        self.assertEqual((fourth_failed["looks"], fourth_failed["level"]), (4, evidence.HOLDOUT_ALPHA / 5))
        self.assertGreater(fourth_failed["sharpe"], base["sharpe"], "it moves when a look is made")
        passed_only = bar_after([(True, 0.001)])
        self.assertEqual(passed_only, bar_after([(False, 0.9)]))
        self.assertGreater(passed_only["level"], 0)
        # The gate's own level after a pass is looser: the printed bar is the most it can ask, never less than it asks.
        self.assertGreaterEqual(evidence.holm_level([0.001]), passed_only["level"])
        self.assertGreaterEqual(evidence.holm_level([0.836, 0.831, 0.996, 0.001]), fourth_passed["level"])
        # A look in flight (any family's) counts as one made, and no outcome is known of it.
        bar_after(failed)
        self.family("flying")
        self.store.set_state("flying", look_inflight={"sha": "x", "at": self.clock()})
        self.assertEqual(power_bar(self.store, self.settings), fourth_failed)
        import inspect

        from league.swarm import researcher
        source = inspect.getsource(researcher.power_bar)
        self.assertNotIn("p_value", source)
        self.assertNotIn(".looks()", source, "the count alone leaves the store (`looks_made`): no look's row is read")

    def test_a_family_with_no_version_yet_reads_the_unit_limits(self):
        self.family("new")
        self.store.update_family("new", best_version=None)
        text = self.me().gate_text(self.store.family("new"))
        self.assertEqual(text, "The unit: a version is validated only while one structure of it risks at most $80.00 at its "
                               "median on Train (its maximum loss a contract), and goes to the gate only while that is at most "
                               "$100.00 over the Validation year (what a first real-money position may risk a contract; the "
                               "Validation year's is usually the larger).")
        self.assertIn(text, self.me().status(self.store.family("new")), "from its first cycle")

    def test_with_every_screen_off_the_status_says_nothing_of_them(self):
        self.family_with("a")
        self.settings["gate"]["look_holds"] = None
        self.settings["researcher"].update(max_unit_usd=None, max_unit_train_usd=None)
        self.assertEqual(self.me().gate_text(self.store.family("a")), "")
        self.store.set_state("a", best_train_version=None)
        self.store.update_family("a", best_version=None)
        self.assertEqual(self.me().gate_text(self.store.family("a")), "")


# -------------------------------------------------------------------------------------------- 6. the program in sight
class TheProgramInSight(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.fid = self.fam["id"]

    def bodies(self) -> list[str]:
        """The user messages of the latest call."""
        return [i["content"] for i in self.sail.bodies[-1]["input"] if isinstance(i, dict) and i.get("role") == "user"]

    def shown(self) -> list[str]:
        return [m for m in self.bodies() if m.startswith(PROGRAM_HEAD)]

    def hold(self) -> None:
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing new"})]}]
        self.researcher().cycle(self.fid)

    def test_a_fork_is_handed_its_parents_program_before_its_first_turn(self):
        child = self.store.add_family({**family_spec_of(self.spec), "id": "condor-vrp-on-qqq"}, origin="fork", parent=self.fid)
        self.store.add_version(child["id"], self.code, {"vrp_min": 1.4}, author=f"fork of {self.fid}",
                               note="the parent's version 7 on SPY, QQQ")
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "reading"})]}]
        self.researcher().cycle(child["id"])
        [program] = self.shown()
        self.assertTrue(program.startswith("YOUR PROGRAM (version 1, your latest version: what gym_run reruns with no `code`"))
        self.assertIn(f"It is {self.fid}'s program, handed to you whole (the parent's version 7 on SPY, QQQ): revise it", program)
        self.assertIn('Its params: {"vrp_min": 1.4}.', program)
        self.assertIn(f"```python\n{self.code}\n```", program, "whole, as the Gym has it")
        users = self.bodies()
        self.assertLess(users.index(program), len(users) - 1, "before the status, which closes the turn's input")
        self.assertTrue(users[-1].startswith("Cycle 1."))

    def test_a_revival_is_handed_the_program_it_revives(self):
        child = self.store.add_family({**family_spec_of(self.spec), "id": "condor-vrp-r"}, origin="operator", parent=self.fid)
        self.store.add_version(child["id"], self.code, {}, author="operator-revive", note="revived for the current evaluator")
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "reading"})]}]
        self.researcher().cycle(child["id"])
        self.assertIn(f"It is {self.fid}'s program, handed to you whole", self.shown()[0])

    def fresh(self) -> list[str]:
        """The program messages the latest cycle added (a showing of an earlier cycle rides in the history)."""
        cycles, _ = self.store.convo(self.fid)
        return [str(i["content"]) for i in cycles[-1]["items"] if str(i.get("content") or "").startswith(PROGRAM_HEAD)]

    def test_it_is_shown_when_the_history_no_longer_holds_it_and_once(self):
        self.researcher().cycle(self.fid)  # the starter's cycle: its message carries the program
        starter = self.store.version(self.fid, 1)["code"]
        self.hold()
        self.assertEqual(self.shown(), [], "the starter's message is the history's last cycle, whole")
        better = starter + "\n# a revision\n"
        self.steps = [{"calls": [("gym_run", {"code": better})]}, {"text": "read"}]
        self.researcher().cycle(self.fid)
        [first] = self.fresh()
        self.assertIn(f"```python\n{starter}\n```", first, "the starter's message was shortened by now: version 1, whole")
        shows = []
        for _ in range(9):  # holds: the history is cut in chunks, and the run call that carried the revision leaves it
            self.hold()
            shows.append(self.fresh())
        self.assertEqual(shows[0], [], "its own gym_run call carries the revision, and the starter's showing is in the history")
        when = [i for i, s in enumerate(shows) if s]
        self.assertTrue(when, "shown again once that call left the history")
        for i in when:
            # The latest version (the revision) and the best (version 1: the revision did not beat it), each once.
            self.assertEqual(len(shows[i]), 2)
            self.assertIn("(version 2, your latest version", shows[i][0])
            self.assertIn(f"```python\n{better}\n```", shows[i][0])
            self.assertIn("(version 1, your best version, another program than your latest)", shows[i][1])
            self.assertIn(f"```python\n{starter}\n```", shows[i][1])
        self.assertTrue(all(b - a >= 2 for a, b in zip(when, when[1:])), "a showing serves the cycles it stays in the history")
        self.assertLessEqual(len(when), 4, "not every cycle")

    def test_the_best_is_shown_too_when_it_is_another_program(self):
        self.researcher().cycle(self.fid)
        worse = self.code + "\n# an experiment\n"
        self.store.add_version(self.fid, worse, {}, author="model")
        for _ in range(5):
            self.hold()
        me = self.researcher()
        self.store.update_family(self.fid, best_version=1)
        fam = self.store.family(self.fid)
        items = me.program_items(fam, [])
        self.assertEqual(len(items), 2)
        self.assertIn("version 2, your latest version", items[0]["content"])
        self.assertIn(worse, items[0]["content"])
        self.assertIn("version 1, your best version, another program than your latest", items[1]["content"])
        self.assertIn(self.store.version(self.fid, 1)["code"], items[1]["content"])
        self.assertEqual(me.program_items(fam, items), [], "both are in sight then")
        same = self.store.add_version(self.fid, worse, {"vrp_min": 1.5}, author="model")
        self.store.update_family(self.fid, best_version=2)
        self.assertEqual(len(me.program_items(self.store.family(self.fid), [])), 1, f"version {same['n']} is version 2's code")

    def test_in_sight_reads_a_run_calls_code_and_a_message_and_trim_keeps_a_showing_whole(self):
        code = "x" * 9000
        call = {"type": "function_call", "name": "gym_run", "call_id": "c", "arguments": json.dumps({"code": code})}
        self.assertTrue(in_sight([call], code))
        self.assertTrue(in_sight([{**call, "arguments": {"code": code}}], code))
        self.assertFalse(in_sight([{**call, "name": "notebook"}], code))
        self.assertFalse(in_sight([{**call, "arguments": json.dumps({"params": {}})}], code))
        self.assertFalse(in_sight([{"role": "user", "content": code[:-1]}], code), "a cut copy is not the program")
        shown = {"role": "user", "content": f"{PROGRAM_HEAD} (version 1): {code}"}
        long = {"role": "user", "content": "y" * 9000}
        trimmed = self.researcher().trim([{"cycle": 1, "items": [shown, long]}, {"cycle": 2, "items": []}])
        self.assertEqual(trimmed[0]["items"][0], shown, "a showing stays whole while its cycle is in the history")
        self.assertTrue(trimmed[0]["items"][1]["content"].endswith("...(shortened)"))

    def test_the_switch(self):
        self.settings["researcher"]["show_program"] = False
        self.store.add_version(self.fid, self.code, {}, author="seed")
        self.assertEqual(self.researcher().program_items(self.store.family(self.fid), []), [])
        self.settings["researcher"]["show_program"] = True
        self.assertEqual(len(self.researcher().program_items(self.store.family(self.fid), [])), 1)


def family_spec_of(spec: dict) -> dict:
    from league.swarm.seeds import family_spec

    out = family_spec(spec)
    out.pop("signal", None)  # a fork's first version is its parent's program, not a starter
    return out


# -------------------------------------------------------------------------------------------- 7. the zero-trade probe
class TheProbe(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.settings["researcher"]["probe_year"] = 2022
        self.fid = self.fam["id"]
        self.store.update_family(self.fid, roots=["SPY", "QQQ", "IWM"])
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=0 if job.purpose == "probe" else 150)

    def test_the_probe_runs_on_every_root_the_full_run_would_trade(self):
        out: dict = {"tool_calls": 0}
        code = self.code.replace("'roots': ['SPY']", "'roots': ['SPY', 'QQQ', 'IWM']")
        view = self.researcher()._gym_run(self.store.family(self.fid), {"code": code}, out, author="synthetic")
        [job] = self.pool.jobs
        self.assertEqual((job.purpose, job.roots, job.start, job.end), ("probe", ("SPY", "QQQ", "IWM"), "2022-01-01", "2022-12-31"))
        self.assertEqual(view["reason"], "disqualified: no trades in the probe year (2022 on SPY, QQQ, IWM)")
        self.assertIn("could not be eligible", view["next"])
        self.assertIn("full=true", view["next"])
        full = self.researcher()._gym_run(self.store.family(self.fid), {"code": code, "full": True}, {"tool_calls": 0},
                                          author="synthetic")
        self.assertEqual((full["status"], self.pool.jobs[-1].purpose, self.pool.jobs[-1].roots),
                         ("ok", "train", ("SPY", "QQQ", "IWM")), "full=true runs the whole of Train on the same roots")


# -------------------------------------------------------------------------------------------- 8. the settings as code
class TheSettings(unittest.TestCase):
    def test_the_committed_policy_and_the_defaults(self):
        policy = json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8"))["researcher"]
        self.assertEqual({k: policy[k] for k in ("carrier_screen", "max_unit_usd", "max_unit_train_usd", "probe_year",
                                                 "show_program", "extension_hold_days")},
                         {"carrier_screen": True, "max_unit_usd": 100, "max_unit_train_usd": 80, "probe_year": 2022,
                          "show_program": True, "extension_hold_days": 7})
        defaults = S.DEFAULTS["researcher"]
        self.assertEqual((defaults["carrier_screen"], defaults["max_unit_usd"], defaults["max_unit_train_usd"],
                          defaults["show_program"], defaults["probe_year"], defaults["extension_hold_days"]),
                         (True, 100.0, 80.0, True, None, 7), "the probe's default stays off: the policy switches it on")
        loaded = S.load(config={}, policy=json.loads(REAL_POLICY_PATH.read_text(encoding="utf-8")))
        self.assertEqual(loaded["_policy"]["state"], "ok")
        with patch("league.swarm.gate.SEALED_LOOKS", True):
            self.assertEqual((max_unit(loaded), max_unit_train(loaded), carrier_share(loaded), loaded["researcher"]["probe_year"]),
                             (100.0, 80.0, 0.25, 2022))
        off = S.load(config={}, policy={"researcher": {"max_unit_usd": None, "max_unit_train_usd": None}})
        self.assertEqual((off["_policy"]["state"], max_unit(off), max_unit_train(off)), ("ok", None, None),
                         "null in the policy turns each unit screen off")


# ------------------------------------------------------------------------------------- 9. the contract and the architect
class TheWords(RoundCase):
    FOUR = ("Many near-independent bets", "A small unit", "Profit that survives the natural spread", "Timing, not the market's drift")

    def test_the_contract_says_what_reaches_real_money_where_it_says_how_to_work(self):
        text = CONTRACT.read_text(encoding="utf-8")
        how = text[text.index("## How to work"):]
        game = text[text.index("## The game you are in"):text.index("## Your tools")]
        self.assertIn("Build for what reaches real money", how)
        for line in self.FOUR:
            self.assertIn(line, how)
            self.assertNotIn(line, game, "the game's own section is another's to write")
        self.assertIn("Let a rule pick the direction, calls or puts", how)
        tools = text[text.index("## Your tools"):text.index("## How to work")]
        self.assertIn("gym_run(code?, params?, stress?, full?, why?, note?)", tools)
        self.assertIn("**Your program.**", tools)
        for words in (how, SYSTEM):
            self.assertNotIn("0.25", words)
            self.assertNotIn("25%", words)
            self.assertNotIn("holdout look", words.lower().replace("a sealed holdout at the gate", ""))

    def test_the_architect_is_told_the_same_and_its_request_states_the_unit(self):
        self.assertIn("WHAT REACHES REAL MONEY, on the swarm's own Train and Validation record", SYSTEM)
        said = " ".join(SYSTEM.split())
        for words in ("Many near-independent bets", "A small unit", "An edge larger than its round trip",
                      "Timing, not the market's drift", "never a standing long"):
            self.assertIn(words, said)
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertIn("UNIT (researcher.max_unit_train_usd): one structure of a family's program may risk at most $80 at its "
                      "median on Train", arch.prompt())
        self.settings["researcher"]["max_unit_train_usd"] = 250
        self.assertIn("may risk at most $250 at its median on Train", arch.prompt())
        self.settings["researcher"]["max_unit_train_usd"] = None
        self.assertNotIn("UNIT (researcher.max_unit_train_usd)", arch.prompt())


if __name__ == "__main__":
    unittest.main()

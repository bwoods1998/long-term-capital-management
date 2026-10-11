"""Release E1's review fixes on the swarm, evidence, ops and docs side (the adversarial review of feat/equity-e1, Oct 10,
2026; findings by id in each test's docstring). One file, so the four fixers' branches never meet in a test file.

The swarm tests run on league/tests/test_elane_gate.py's harness (the runner and the screen faked at their interfaces);
the `World` cases run the real things on a SYNTHETIC store (league/equity/synth.py; never market data): the real
SwarmStore, Tournament and Gate, `runner.Isolated` over an `InlineDecider`, the real screen under the FAKE receipt 2."""

from __future__ import annotations

import json
import sys
import unittest
from unittest import mock

from league.equity import BETA, EQUITY_ENGINE_VERSION
from league.equity import screen as S
from league.swarm import elane
from league.swarm.evaluator import EQUITY_SELECTION_KEYS, adopt_equity
from league.swarm.gate import run_sha
from league.tests.test_elane import CODE, ON
from league.tests.test_elane_gate import EquityCase, FakeRunner, screen
from league.tests.test_swarm_loop import LoopCase

#: The screen's own lineage rule (league/tests/test_elane_gate.py `screen` fakes it; these tests judge with the real one).
REAL_SAME_LINEAGE = S.same_lineage
MOVED = {"equity": "e" * 64, "engine": EQUITY_ENGINE_VERSION}


class PickyRunner(FakeRunner):
    """`FakeRunner` whose Train-era runs fail for the families named in `broken`, and whose runs end with the status
    `ended` names for their window ("segment-1", "segment-2", "validation", "holdout"; else the runner's own)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.broken: set[str] = set()
        self.ended: dict[str, str] = {}

    def _run(self, name, window, k):
        run = super()._run(name, window, k)
        run.result["status"] = self.ended.get(window, run.result["status"])
        return run

    def segments(self, code, params, *, name):
        if name in self.broken:
            self.calls.append(("segments", name))
            raise RuntimeError("the child failed")
        return super().segments(code, params, name=name)


class FixCase(EquityCase):
    def setUp(self):
        super().setUp()
        self.runner = PickyRunner()
        self.tournament.equity_runner = self.gate.equity_runner = self.runner

    def ready(self, fid="b1", **kw):
        version = self.born(fid, **kw)
        self.validated(fid)
        return version, run_sha(version)

    def looked(self, fid="b1", **kw):
        version, sha = self.ready(fid, **kw)
        with screen():
            self.assertTrue(self.gate.look(self.store.family(fid), version, sha))
        return version, sha

    def gate_round(self, **kw):
        """One equity round of the gate, D3 judged by the screen's real `same_lineage`."""
        out = {"looked": [], "refused": [], "waiting": [], "held": [], "look_held": []}
        with screen(**kw) as mint, mock.patch.object(S, "same_lineage", REAL_SAME_LINEAGE):
            self.gate.equity_round(out)
        return out, mint

    def actions(self, fid, kind="swarm.gate"):
        return [e["payload"].get("action") for e in self.store.events_after(0, limit=100_000)
                if e["kind"] == kind and e.get("family") == fid]


class LineageRecord(FixCase):
    """s2-1 and evidence-2 (one defect): an equity identity adoption cleared `elane_train_r`, the Train series D3's
    correlation test reads, for families already looked at, so a re-coded copy of a looked-at program got its own
    sealed look."""

    def test_an_adoption_keeps_the_looks_lineage_record_and_d3_still_binds(self):
        self.looked("b1")
        kept = self.store.family("b1")["state"]
        self.assertTrue(kept[elane.TRAIN_R_KEY]["days"])
        outcome = adopt_equity(self.store, MOVED)  # the next release moved an evidence module
        self.assertEqual((outcome["adopted"], outcome["families"]), (True, 1))
        state = self.store.family("b1")["state"]
        self.assertEqual(state[elane.TRAIN_R_KEY], kept[elane.TRAIN_R_KEY], "the look's lineage record is kept")
        self.assertEqual(state[elane.TEMPLATE_KEY], kept[elane.TEMPLATE_KEY])
        self.assertEqual(state[elane.LOOK_KEY], kept[elane.LOOK_KEY])
        self.assertIsNone(state[elane.FLOOR_KEY], "the floor is evidence under the old engine: cleared")
        self.assertNotIn(elane.TRAIN_R_KEY, EQUITY_SELECTION_KEYS)
        self.assertNotIn(elane.TRAIN_R_KEY, state["previous_evaluator_selection"])
        # A re-coded copy: another code sha (so another template), the very same Train-era returns.
        self.ready("b2", code=CODE + "# the same rule, other bytes\n")
        out, mint = self.gate_round()
        self.assertEqual((out["looked"], mint.call_count, len(self.looks())), ([], 0, 1), "no second sealed look")
        (refusal,) = self.store.refusals("b2")
        self.assertEqual(refusal["stage"], "same lineage")
        self.assertIn("b1", refusal["reason"])

    def test_a_looked_at_program_with_no_series_has_it_written_again(self):
        """D3 fails closed: the series is written again from the looked version's Train-era runs, and binds."""
        self.looked("b1")
        was = self.store.family("b1")["state"][elane.TRAIN_R_KEY]
        self.store.set_state("b1", **{elane.TRAIN_R_KEY: None})
        self.ready("b2", code=CODE + "# the same rule, other bytes\n")
        self.runner.calls.clear()
        out, mint = self.gate_round()
        self.assertEqual((out["looked"], mint.call_count, len(self.looks())), ([], 0, 1))
        self.assertEqual(self.store.refusals("b2")[0]["stage"], "same lineage")
        self.assertEqual(self.store.family("b1")["state"][elane.TRAIN_R_KEY], was)
        self.assertIn(("segments", "b1"), self.runner.calls, "its looked version's Train-era runs")
        self.assertNotIn("look", [c[0] for c in self.runner.calls], "nothing sealed is read for it")
        self.assertIn("equity_lineage_restored", self.actions("b1"))

    def test_a_series_that_cannot_be_written_again_makes_the_look_wait(self):
        self.looked("b1")
        self.store.set_state("b1", **{elane.TRAIN_R_KEY: None})
        self.runner.broken = {"b1"}
        version, sha = self.ready("b2", code=CODE + "# another program\n")
        out, mint = self.gate_round()
        self.assertEqual((out["looked"], mint.call_count, len(self.looks())), ([], 0, 1), "never passes D3 unjudged")
        state = self.store.family("b2")["state"]
        self.assertEqual((state["gate_ready"], state["gate_outcome"]["result"], state.get("look_inflight")),
                         (True, "waiting", None))
        self.assertIn("b1", state["gate"])
        self.assertEqual(self.store.refusals("b2"), [], "a wait, not a refusal: nothing is spent")
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b2"), ON))
        self.runner.broken = set()
        out, mint = self.gate_round()
        self.assertEqual(self.store.refusals("b2")[0]["stage"], "same lineage", "judged once the series is back")

    def test_a_look_in_flight_elsewhere_waits_and_a_retired_marker_is_no_look(self):
        version, sha = self.ready("b2", code=CODE + "# another program\n")
        self.born("b1")
        template = elane.lineage_key(BETA, "0" * 64)
        self.store.set_state("b1", look_inflight={"sha": "s" * 64, "n": 1, "at": self.clock()},
                             **{elane.TEMPLATE_KEY: template})
        with screen(), mock.patch.object(S, "same_lineage", REAL_SAME_LINEAGE):
            with self.assertRaises(elane.LineageUnread) as raised:
                elane.same_lineage(self.store, self.store.family("b2"), BETA, "beta:x", {"days": [1, 2, 3], "r": [0.1, 0.2, 0.3]})
            self.assertEqual(raised.exception.family, "b1")
            self.assertIsNone(self.gate.look(self.store.family("b2"), version, sha), "it waits for the look in flight")
            self.assertEqual(self.looks(), [])
            self.store.retire("b1", "retired by hand")
            self.assertIsNone(elane.same_lineage(self.store, self.store.family("b2"), BETA, "beta:x",
                                                 {"days": [1, 2, 3], "r": [0.1, 0.2, 0.3]}),
                              "a retired family's marker of a look that never landed: nothing was looked at")


class EquityRoundsOnTheirOwn(LoopCase):
    """s2-7: the equity Validation round and the equity look ran only inside the options rounds (`Tournament.run` after
    the options Validation, `Gate.run`), which the loop starts only while the guard allows and the Gym is ready. A3: an
    equity run needs no Gym box and no model dollar, so the brake, a Gym that is down and a failed options round must
    not hold a seed's Validation or its look."""

    def on(self, **gym):
        """The lanes on in swarm.json (the loop reads it each pass), the Gym as given."""
        self.settings["elane"] = {"mode": "gate"}
        self.settings["gym"].update(gym)
        (self.root / "swarm.json").write_text(json.dumps({"enabled": True, "gym": self.settings["gym"],
                                                          "researcher": {"idle_seconds": 0}, "elane": {"mode": "gate"}}))
        sw = self.swarm()
        sw.tournament.equity_runner = sw.gate.equity_runner = FakeRunner()
        return sw

    def passed(self, sw):
        """One main-loop pass with the screen faked at its interfaces, its rounds joined."""
        with screen():
            sw.step()
            for thread in list(sw.rounds.values()):
                thread.join(30)

    def test_they_run_under_the_brake_and_with_the_gym_down(self):
        sw = self.on(enabled=False, image_checkpoint=None)
        self.guard.braked = True
        self.guard.reason = "today's research is at its cap"
        self.assertFalse(sw.gym_ready())
        self.passed(sw)
        self.assertEqual(set(sw.rounds), {"equity"}, "no options round starts under the brake; the equity rounds do")
        self.assertIsNone(self.store.get("tournament_at"))
        self.assertIsNone(self.store.get("gate_at"))
        seeds = [f["id"] for f in self.store.families(lanes=elane.LANES)]
        self.assertEqual(sorted(seeds), ["seed-overnight-qqq", "seed-overnight-spy", "seed-reversal-index"])
        for fid in seeds:
            fam = self.store.family(fid)
            self.assertEqual((fam["validated_version"], fam["state"][elane.TRY_KEY]["entered"]), (1, True), fid)
        looked = [(look["family"], look["passed"]) for look in self.store.looks()]
        self.assertEqual(len(looked), 3, "validated and looked at in the same round")
        self.assertEqual({f["band"] for f in self.store.families(lanes=elane.LANES)}, {"candidate"})
        beat = json.loads((self.root / "swarm.heartbeat").read_text())["status"]
        self.assertTrue(beat["braked"])
        self.assertEqual((beat["equity"]["mode"], beat["equity"]["round_at"]), ("gate", self.store.get(elane.ROUND_KEY)))
        # The funnel counts the round's verdicts from their own events (the hourly tournament row never held them).
        from league.ops import funnel

        counts = funnel.window(self.root, sw.clock() - 3600, sw.clock() + 1)["equity"]["beta"]
        self.assertEqual((counts["births"], counts["validations"], counts["looks"]),
                         (3, {"judged": 3, "passed": 3}, {"taken": 3, "passed": 3}))

    def test_the_options_rounds_never_carry_them_and_a_failed_one_costs_them_nothing(self):
        sw = self.on()
        self.store.put("tournament_at", 0.0)
        sw.tournament.validate = mock.Mock(side_effect=RuntimeError("the options Validation failed"))
        with mock.patch.object(sw.tournament, "equity_round", wraps=sw.tournament.equity_round) as step, \
                mock.patch.object(sw.gate, "equity_round", wraps=sw.gate.equity_round) as looks:
            self.passed(sw)
            self.assertEqual((step.call_count, looks.call_count), (1, 1), "once each: on the equity thread alone")
        self.assertLessEqual({"tournament", "gate", "equity"}, set(sw.rounds))
        sw.tournament.validate.assert_called_once()
        self.assertEqual(len(self.store.looks()), 3, "the failed options round cost the seeds nothing")

    def test_the_pace_and_the_switch(self):
        sw = self.on()
        self.assertTrue(sw.equity_due())
        self.passed(sw)
        self.assertFalse(sw.equity_due(), "one round every elane.ROUND_SECONDS")
        self.store.put(elane.ROUND_KEY, sw.clock() - elane.ROUND_SECONDS - 1)
        self.assertTrue(sw.equity_due())
        sw.settings["elane"] = {"mode": "off"}
        self.assertFalse(sw.equity_due(), "the lanes off: nothing runs")
        sw.settings["elane"] = {"mode": "gate"}
        with mock.patch.object(sw.tournament, "equity_round", side_effect=RuntimeError("boom")), screen():
            out = sw.equity_rounds()
        self.assertEqual(out["errors"], {"round": "RuntimeError"}, "never raises; the gate's step still ran")


class TheOrderOfTheLooks(FixCase):
    """s2-6 and evidence-9 (one defect): the seeds' looks ran in (born_at, id) order with born_at to the second, so in
    the ids' alphabet (QQQ before SPY), or by a clock tick; under D3 the later of two seeds of one lineage is refused
    with no look, and it then retired as "used its one Validation try", which is not what happened."""

    def seeded(self):
        born = elane.birth_seeds(self.store, ON)
        self.assertEqual(len({self.store.family(fid)["born_at"] for fid in born}), 1, "one clock reading: one second")
        with screen():
            self.tournament.equity_round()
        return born

    def test_the_looks_are_taken_in_the_seed_lists_order(self):
        from league.swarm import seeds

        listed = [str(spec["id"]) for spec in seeds.EQUITY_SEEDS]
        self.assertEqual(listed[:2], ["seed-overnight-spy", "seed-overnight-qqq"], "SPY's overnight seed goes first")
        self.assertNotEqual(listed, sorted(listed), "the list's order is not the alphabet's")
        self.assertEqual(self.seeded(), listed)
        fams = self.store.families(alive=True, lanes=elane.LANES)
        self.assertEqual([f["id"] for f in fams], sorted(listed), "the store's order: born in one second, by id")
        self.assertEqual([f["id"] for f in elane.round_order(self.store, fams)], listed)
        self.runner.calls.clear()
        out, mint = self.gate_round()  # every seed's Train series is the harness's one series: one lineage
        self.assertEqual(out["looked"], [{"family": "seed-overnight-spy", "passed": True, "lane": BETA}])
        self.assertEqual([c[1] for c in self.runner.calls if c[0] == "look"], ["seed-overnight-spy"])
        for fid in listed[1:]:
            (refusal,) = self.store.refusals(fid)
            self.assertEqual(refusal["stage"], "same lineage")
            self.assertIn("seed-overnight-spy", refusal["reason"])

    def test_a_later_birth_keeps_its_place_and_an_unseeded_family_follows_the_seeds(self):
        self.born("aaa-first")  # born before the seeds: its turn is first, whatever its id
        self.clock.advance(5)
        born = elane.birth_seeds(self.store, ON)
        self.born("aaa-same-second", seeded=False)
        self.clock.advance(5)
        self.born("aaa-later")
        fams = self.store.families(alive=True, lanes=elane.LANES)
        self.assertEqual([f["id"] for f in elane.round_order(self.store, fams)],
                         ["aaa-first", *born, "aaa-same-second", "aaa-later"])
        with mock.patch.object(self.store, "get", side_effect=RuntimeError("unreadable")):
            self.assertEqual(elane.round_order(self.store, fams), fams, "a store that cannot say: the order as given")

    def test_a_version_refused_before_its_look_retires_for_what_happened(self):
        self.seeded()
        self.gate_round()
        with screen():
            out = self.tournament.equity_round()
        self.assertEqual(out["retired"], ["seed-overnight-qqq", "seed-reversal-index"])
        for fid in out["retired"]:
            fam = self.store.family(fid)
            self.assertEqual(fam["retire_reason"], elane.SAME_LINEAGE)
            self.assertNotEqual(fam["retire_reason"], elane.SPENT_TRY, "its try was not what ended it")
        self.assertNotRegex(elane.SAME_LINEAGE + elane.FLOOR_INELIGIBLE + elane.REFUSED_BEFORE_LOOK, r"seed-|\$",
                            "public causes: the rule's words, no family and no figure")
        self.assertEqual(self.store.family("seed-overnight-spy")["band"], "candidate", "the one that was judged")

    def test_an_ineligible_floor_and_a_failed_recheck_have_their_own_causes(self):
        version, sha = self.ready("b1")
        with screen(eligible=False):
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.FLOOR_INELIGIBLE)
        version, sha = self.ready("b2", code=CODE + "# another program\n")
        with screen(precheck=False):
            self.assertIsNone(self.gate.look(self.store.family("b2"), version, sha))
        self.assertEqual(self.store.refusals("b2")[0]["stage"], "precheck")
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b2"), ON), elane.REFUSED_BEFORE_LOOK)
        # A failed Validation try, and a spent look, keep their own words.
        self.born("b3", code=CODE + "# a third program\n")
        self.validated("b3", precheck=False)
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b3"), ON), elane.SPENT_TRY)


class TheRunsStatus(FixCase):
    """s2-2: `look` never read the holdout run's status, so a run its own errors ended ("disqualified") was judged on
    its partial series and could pass, while Validation refuses any status but "ok". The Train-era runs fed the floor
    the same way."""

    def test_a_disqualified_holdout_run_is_a_spent_failed_look_never_a_pass(self):
        version, sha = self.ready()
        self.runner.ended = {"holdout": "disqualified"}
        with screen(passed=True) as mint:
            self.assertIs(self.gate.look(self.store.family("b1"), version, sha), False)
        self.assertEqual(mint.verdict.call_count, 0, "a partial series is never judged")
        (look,) = self.looks()
        self.assertEqual((look["passed"], look["detail"]["status"], look["detail"]["passed"]), (0, "disqualified", False))
        fam = self.store.family("b1")
        state = fam["state"]
        self.assertEqual((fam["band"], state["gated_sha"], state["gate_ready"], state["gate"], state.get("look_inflight")),
                         ("gym", sha, False, "fail", None))
        self.assertEqual((state[elane.LOOK_KEY]["verdict"]["passed"], state[elane.LOOK_KEY]["verdict"]["status"]),
                         (False, "disqualified"))
        self.assertNotIn("banded_evaluator", state, "no band proof")
        self.assertTrue(state[elane.TRAIN_R_KEY]["days"], "the look is spent: its lineage record is kept for D3")
        self.assertEqual(elane.lineage_spent(self.store, fam, ON), elane.SPENT_LOOK)
        with screen():
            self.assertEqual(self.tournament.equity_round()["retired"], ["b1"])

    def test_a_holdout_run_the_house_could_not_make_is_no_look(self):
        version, sha = self.ready()
        self.runner.ended = {"holdout": "no_data"}
        with screen() as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        state = self.store.family("b1")["state"]
        self.assertEqual((self.looks(), mint.verdict.call_count, state["gate_ready"], state.get("look_inflight")),
                         ([], 0, True, None))
        self.assertNotIn(elane.LOST_KEY, state, "the House's failure counts against no program")
        self.runner.ended = {}
        with screen():
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha), "owed again, and taken")

    def test_a_disqualified_train_era_run_refuses_the_floor_before_any_look(self):
        version, sha = self.ready()
        self.runner.ended = {"segment-2": "disqualified"}
        with screen() as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual((self.looks(), mint.call_count, mint.floor.call_count), ([], 0, 0), "no floor from a partial run")
        (refusal,) = self.store.refusals("b1")
        self.assertEqual(refusal["stage"], "screen floor")
        self.assertIn("disqualified", refusal["reason"])
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.FLOOR_INELIGIBLE)

    def test_a_train_era_span_with_no_data_is_no_history_for_the_floor(self):
        version, sha = self.ready()
        self.runner.ended = {"segment-1": "no_data"}
        with screen() as mint:
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))
        (segments,), kw = mint.floor.call_args
        self.assertIsNone(segments[0], "the screen's rule: None where the program has no history")
        self.assertEqual(list(segments[1].days), [10, 11, 12, 13, 14])
        self.assertEqual(self.store.family("b1")["state"][elane.TRAIN_R_KEY]["days"], [10, 11, 12, 13, 14])


class TheSealedRunSentOnce(FixCase):
    """s2-4: a look whose run did not return was owed again with nothing recorded, without limit, so a program that
    stops answering when its holdout goes badly could be shown its holdout again; and the evidence child's hash seed
    was random, so the next run could differ."""

    def test_a_sealed_run_that_does_not_return_is_owed_once_then_the_look_is_spent(self):
        from league.equity.runner import RunLost

        version, sha = self.ready()
        self.runner.look_error = RunLost("the decider child failed the run: the child was killed")
        with screen() as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        state = self.store.family("b1")["state"]
        self.assertEqual((self.looks(), state["gate_ready"], state.get("look_inflight")), ([], True, None))
        self.assertEqual((state[elane.LOST_KEY]["sha"], state[elane.LOST_KEY]["count"]), (sha, 1))
        alerts = [e["payload"] for e in self.store.events_after(0, limit=100_000)
                  if e["kind"] == "swarm.status" and e["payload"].get("action") == "equity_look_lost"]
        self.assertEqual([(a["alert"], a["count"], a["spent"]) for a in alerts], [(True, 1, False)], "a House warning")
        with screen() as mint:
            self.assertIs(self.gate.look(self.store.family("b1"), version, sha), False)
        (look,) = self.looks()
        self.assertEqual((look["passed"], look["detail"]["status"]), (0, "lost"))
        self.assertEqual(mint.verdict.call_count, 0)
        self.assertEqual(elane.LOOK_SENDS, 2)
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_LOOK)
        self.assertEqual([c[0] for c in self.runner.calls].count("look"), 2, "its holdout was sent twice, never a third time")

    def test_a_house_failure_before_the_send_is_owed_and_counts_against_nobody(self):
        from league.equity.runner import RunFailed
        from league.equity.store import StoreRefused

        version, sha = self.ready()
        for error in (RunFailed("the decider child failed the needs"), StoreRefused("the store cannot be read"),
                      RuntimeError("the child died")) * 2:
            self.runner.look_error = error
            with screen():
                self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        state = self.store.family("b1")["state"]
        self.assertEqual((self.looks(), state["gate_ready"]), ([], True))
        self.assertNotIn(elane.LOST_KEY, state)
        self.runner.look_error = None
        with screen():
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))

    def test_the_runner_tells_a_run_that_was_sent_from_one_that_was_not(self):
        import datetime as dt
        import tempfile
        from pathlib import Path

        from league.equity import runner as R
        from league.equity import synth
        from league.equity.program import CodeRefused

        class Child:
            """A decider whose "needs" answers and whose "run" does what `run` says."""

            def __init__(self, run):
                self.run, self.ops = run, []

            def kind(self, kind, op, payload, *, budget_seconds=None):
                self.ops.append(op)
                if op == "needs":
                    return {"ok": True, "needs": {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}}
                if isinstance(self.run, Exception):
                    raise self.run
                return self.run

        with tempfile.TemporaryDirectory() as tmp:
            root = synth.constant_store(Path(tmp) / "store", start=dt.date(2025, 1, 2), sessions=30)
            for run in (TimeoutError("the decider did not answer in time"), {"ok": False, "error": "the child broke"},
                        {"ok": True, "result": None}, {"ok": True, "result": {"status": "error", "reason": "engine"}}):
                with self.assertRaises(R.RunLost, msg=repr(run)):
                    R.Isolated(Child(run), root).validation(CODE, {}, name="p")
            self.assertTrue(issubclass(R.RunLost, R.RunFailed), "every earlier reader of RunFailed still catches it")
            with self.assertRaises(CodeRefused):
                R.Isolated(Child({"ok": False, "refused": True, "error": "no decide"}), root).validation(CODE, {}, name="p")
            child = Child({"ok": True, "result": {"status": "ok"}})
            child.kind = mock.Mock(side_effect=TimeoutError("the decider did not answer in time"))
            with self.assertRaises(R.RunFailed) as raised:
                R.Isolated(child, root).validation(CODE, {}, name="p")
            self.assertNotIsInstance(raised.exception, R.RunLost, "the NEEDS call failed: nothing was sent")

    def test_the_evidence_child_pins_its_hash_seed(self):
        import tempfile

        from league.live import decider as D

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(elane._runners, {}, clear=True):
            runner = elane.isolated_runner(tmp)
            self.assertEqual((runner.decider.hash_seed, elane.EVIDENCE_HASH_SEED), (0, 0))
        self.assertIsNone(D.Decider.hash_seed, "every other child is as it was (the options book's, the equity book's)")
        spawned: list[tuple] = []

        def popen(command, **kw):
            spawned.append((list(command), dict(kw.get("env") or {})))
            raise OSError("not started: the command and its environment are the test")

        for seed in (None, 0):
            child = D.Decider(allow_unisolated=True)
            child.hash_seed = seed
            child.netns = False
            child._netns_retry_at = float("inf")
            with mock.patch.object(D.subprocess, "Popen", side_effect=popen), self.assertRaises(OSError):
                child._spawn()
        (plain, plain_env), (pinned, pinned_env) = spawned
        self.assertEqual(plain[1:], ["-E", "-s", "-m", "league.live.decider"])
        self.assertNotIn("PYTHONHASHSEED", plain_env)
        self.assertEqual(pinned[1:], ["-s", "-m", "league.live.decider"], "-E would ignore the seed")
        self.assertEqual(pinned_env["PYTHONHASHSEED"], "0")
        self.assertEqual({k for k in pinned_env if k.startswith("PYTHON")}, {"PYTHONHASHSEED"}, "no other PYTHON* name")
        self.assertEqual({k: v for k, v in pinned_env.items() if k != "PYTHONHASHSEED"}, plain_env)


@unittest.skipUnless(sys.platform.startswith("linux"), "the decider child's limits are Linux's")
class TheEvidenceChildIsDeterministic(unittest.TestCase):
    """s2-4, in the real child: a program whose trade follows the iteration order of a set of strings is the same run
    on every start of the evidence child (four starts; unpinned they agree about one time in sixty)."""

    PROGRAM = ("NEEDS = {'symbols': ['SPY', 'QQQ', 'IWM', 'DIA'], 'history': 2}\nPARAMS = {}\n\n\n"
               "def decide(ctx):\n"
               "    if ctx.positions:\n        return []\n"
               "    first = list(set(ctx.symbols))[0]\n"
               "    return [{'buy': first, 'share': 0.2, 'at': 'open', 'tag': 'set-order'}]\n")

    def test_the_same_run_on_every_start(self):
        import tempfile
        from pathlib import Path

        from league.equity import synth
        from league.equity.runner import Isolated
        from league.live import decider as D

        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_store(Path(tmp) / "store", start=__import__("datetime").date(2024, 6, 3),
                                         end=__import__("datetime").date(2025, 3, 31))
            child = D.Decider(python=sys.executable, allow_unisolated=True)
            child.hash_seed = elane.EVIDENCE_HASH_SEED
            self.addCleanup(child.close)
            runner = Isolated(child, root, budget_seconds=120.0)
            seen = set()
            for _ in range(4):
                run = runner.validation(self.PROGRAM, {}, name="set-order")
                self.assertEqual(run.result["status"], "ok")
                seen.add((run.result["result_sha"], tuple(sorted({lot["symbol"] for lot in run.result["lots"]}))))
                child._kill()  # the next run starts a new child (a deploy, a failure)
            self.assertEqual(len(seen), 1, seen)
            self.assertEqual(child.pid is not None and len(next(iter(seen))[1]), 1, "one symbol, bought once")


class ATryOwedAgain(FixCase):
    """s2-3: `next_try` asked only about the family's candidate (its best version, else its newest) or R3's retry while
    the first try's pre-check stood failed, so a validated version that is not the candidate and whose verdict went
    stale was never validated again: the family waited for good. evidence-11: a version validated again re-derived
    R3's retry hash from the versions that exist now."""

    def rounds(self, **kw):
        with screen(**kw), mock.patch.object(S, "retry_permitted", return_value=True):
            return self.tournament.equity_round()

    def test_a_stale_verdict_of_a_version_that_is_no_longer_the_candidate(self):
        """Shape (a): v1 validated and gate-ready, a later v2 exists, an adoption clears best_version."""
        v1 = self.born("b1")
        self.store.update_family("b1", best_version=1)
        self.assertEqual(self.rounds()["validated"]["b1"]["version"], 1)
        self.store.add_version("b1", CODE + "# a later version\n", {}, author="test")
        adopt_equity(self.store, MOVED)
        fam = self.store.family("b1")
        self.assertEqual((fam["best_version"], elane.candidate(fam, self.store)), (None, 2), "the candidate moved to v2")
        self.assertEqual(elane.next_try(self.store, fam, ON), 1, "its own try, owed again: not the candidate's")
        self.assertIsNone(elane.lineage_spent(self.store, fam, ON))
        self.runner.calls.clear()
        out = self.rounds()
        self.assertEqual((out["validated"]["b1"]["version"], out["validated"]["b1"]["entered"]), (1, True))
        self.assertEqual(len(elane.lineage_tries(self.store, "b1")), 1, "the same try: none was spent")
        looked, mint = self.gate_round()
        self.assertEqual(looked["looked"], [{"family": "b1", "passed": True, "lane": BETA}])
        self.assertEqual(self.store.looks()[0]["run_sha"], run_sha(v1))
        self.assertEqual(self.rounds()["validated"], {}, "v2 never takes a try of its own")

    def test_r3s_retry_gone_stale_after_the_stores_daily_write(self):
        """Shape (b): v1 fails its pre-check, R3's retry v2 enters, the data job writes the next day (every result_sha
        moves), the look marks v2 stale."""
        self.born("b1")
        v2 = self.store.add_version("b1", CODE + "# the retry, written before the first try\n", {}, author="test")
        self.store.update_family("b1", best_version=1)
        self.assertEqual(self.rounds(precheck=False)["validated"]["b1"]["entered"], False)
        out = self.rounds()
        self.assertEqual((out["validated"]["b1"]["version"], out["validated"]["b1"]["entered"]), (2, True), "R3's retry")
        self.runner.result_sha = "validation-sha-after-the-daily-write"
        looked, mint = self.gate_round()
        state = self.store.family("b1")["state"]
        self.assertEqual((looked["looked"], state["gate_ready"], state[elane.VERDICTS_KEY]["2"]["stale"]), ([], False, True))
        fam = self.store.family("b1")
        self.assertEqual(elane.next_try(self.store, fam, ON), 2, "the retry is validated again: the same retry")
        self.assertIsNone(elane.lineage_spent(self.store, fam, ON), "never retired unjudged")
        out = self.rounds()
        self.assertEqual((out["validated"]["b1"]["version"], out["validated"]["b1"]["entered"], out["retired"]),
                         (2, True, []))
        looked, mint = self.gate_round()
        self.assertEqual(looked["looked"], [{"family": "b1", "passed": True, "lane": BETA}])
        self.assertEqual(self.store.looks()[0]["run_sha"], run_sha(v2))
        self.assertEqual(len(elane.lineage_tries(self.store, "b1")), 2, "the first try and its one retry, no third")

    def test_a_stale_verdict_of_a_version_that_may_not_be_tried_is_not_asked(self):
        self.born("b1")
        self.store.update_family("b1", best_version=1)
        self.rounds()
        self.store.add_version("b1", CODE + "# never tried\n", {}, author="test")
        state = self.store.family("b1")["state"]
        self.store.set_state("b1", **{elane.VERDICTS_KEY: {**state[elane.VERDICTS_KEY],
                                                           "2": {"entered": True, "at": "x", "stale": True},
                                                           "9": {"entered": True, "at": "x", "stale": True}}})
        self.assertIsNone(elane.next_try(self.store, self.store.family("b1"), ON),
                          "a stale mark buys no try: v2 was never the lineage's try, v9 does not exist")

    def test_the_retry_hash_is_recorded_once_at_the_first_try(self):
        """evidence-11: v1 passes with no later version (retry_sha None); v2 is written afterwards; v1 is validated
        again and fails its pre-check on restated data. v2 was written after the first verdict: no retry."""
        self.born("b1")
        self.store.update_family("b1", best_version=1)
        self.rounds()
        self.assertIsNone(self.store.family("b1")["state"][elane.TRY_KEY]["retry_sha"])
        self.store.add_version("b1", CODE + "# written after the first verdict\n", {}, author="test")
        adopt_equity(self.store, MOVED)
        out = self.rounds(precheck=False)
        self.assertEqual((out["validated"]["b1"]["version"], out["validated"]["b1"]["entered"]), (1, False))
        held = self.store.family("b1")["state"][elane.TRY_KEY]
        self.assertIsNone(held["retry_sha"], "kept as recorded, None included")
        fam = self.store.family("b1")
        self.assertFalse(elane.try_open(self.store, fam, 2, ON))
        self.assertEqual(elane.lineage_spent(self.store, fam, ON), elane.SPENT_TRY)
        self.assertEqual(self.rounds()["retired"], ["b1"])

    def test_a_recorded_retry_hash_survives_the_validation_of_the_retry_and_of_the_first_again(self):
        self.born("b1")
        v2 = self.store.add_version("b1", CODE + "# the retry, written before the first try\n", {}, author="test")
        self.store.add_version("b1", CODE + "# a third version\n", {}, author="test")
        self.store.update_family("b1", best_version=1)
        self.rounds(precheck=False)
        self.assertEqual(self.store.family("b1")["state"][elane.TRY_KEY]["retry_sha"], run_sha(v2))
        self.rounds()  # R3's retry
        self.assertEqual(self.store.family("b1")["state"][elane.TRY_KEY]["version"], 2)
        adopt_equity(self.store, MOVED)
        self.rounds(precheck=False)  # v1 again (the lowest stale): the hash is still v2's, never the newest version's
        held = self.store.family("b1")["state"][elane.TRY_KEY]
        self.assertEqual((held["version"], held["retry_sha"]), (1, run_sha(v2)))


class TheCalendarIsEvidence(unittest.TestCase):
    """evidence-8: the equity identity did not cover the whole import closure of the evidence: the NYSE calendar the
    store's session list and the ctx read (`ltcm.data`, and `ltcm.broker` which it imports) was not hashed, and the CI
    closure test followed only modules named league.*, so it could not see them."""

    @staticmethod
    def import_time(path):
        """The modules `path` imports when it is imported (function bodies left out: they run later, or never)."""
        import ast

        from league.tests.test_equity_identity import REPO

        package = path.relative_to(REPO).with_suffix("").parts[:-1]
        if path.name == "__init__.py":
            package = path.relative_to(REPO).parts[:-1]
        out: set[str] = set()
        pending = list(ast.parse(path.read_text()).body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(node, ast.Import):
                out.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = list(package[:len(package) - node.level + 1]) if node.level else []
                module = ".".join([*base, *(node.module.split(".") if node.module else [])])
                out.add(module)
                out.update(f"{module}.{alias.name}" for alias in node.names)
            pending.extend(ast.iter_child_nodes(node))
        return out

    def outside(self):
        """Every file of the repository outside league/ that importing what the evidence modules import executes."""
        from league.swarm.evaluator import EQUITY_EVIDENCE
        from league.tests.test_equity_identity import REPO, _file_of, _imports, evidence_closure

        pending = [target for name in sorted(evidence_closure(EQUITY_EVIDENCE)) for module in _imports(REPO / name)
                   if not module.startswith("league.") and (target := _file_of(module)) is not None]
        seen: set = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            parts = path.relative_to(REPO).parts
            pending += [init for i in range(1, len(parts)) if (init := REPO.joinpath(*parts[:i], "__init__.py")).is_file()]
            pending += [target for module in self.import_time(path) if (target := _file_of(module)) is not None]
        return {p.relative_to(REPO).as_posix() for p in seen}

    def test_the_hashed_calendar_files_are_what_the_evidence_imports_outside_league(self):
        from league.equity import kinds
        from league.swarm.evaluator import EQUITY_CALENDAR_FILES

        reached = self.outside()
        self.assertEqual({f for f in reached if not f.startswith("league/")}, set(EQUITY_CALENDAR_FILES))
        self.assertEqual(EQUITY_CALENDAR_FILES, ("ltcm/__init__.py", "ltcm/broker.py", "ltcm/data/__init__.py"))
        self.assertLessEqual(set(EQUITY_CALENDAR_FILES), set(kinds.RUNTIME), "the same three the child is given")
        self.assertFalse({f for f in reached if f.startswith("league/")} - {"league/__init__.py"},
                         "the calendar reaches nothing of league/ (it would be evidence too)")

    def test_a_calendar_change_moves_the_equity_identity_and_only_it(self):
        import tempfile
        from pathlib import Path

        from league.gym.driver import LEAGUE_FILES
        from league.swarm.evaluator import (EQUITY_CALENDAR_FILES, EQUITY_EVIDENCE, EQUITY_GYM_FILES,
                                            equity_fingerprint, execution_fingerprint)

        self.addCleanup(equity_fingerprint.cache_clear)
        self.addCleanup(execution_fingerprint.cache_clear)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            names = (*LEAGUE_FILES, *EQUITY_GYM_FILES, *EQUITY_CALENDAR_FILES, "ltcm/data/kalshi.py", "league/live/step.py",
                     *(f"league/equity/{name}.py" for name in EQUITY_EVIDENCE))
            for name in names:
                (repo / name).parent.mkdir(parents=True, exist_ok=True)
                (repo / name).write_text("VALUE = 1\n")
            equity_fingerprint.cache_clear()
            execution_fingerprint.cache_clear()
            original, options = equity_fingerprint(repo), execution_fingerprint(repo)
            for name in EQUITY_CALENDAR_FILES:
                (repo / name).write_text("VALUE = 2  # a holiday rule changed\n")
                equity_fingerprint.cache_clear()
                execution_fingerprint.cache_clear()
                self.assertNotEqual(equity_fingerprint(repo), original, name)
                self.assertEqual(execution_fingerprint(repo), options, "the options identity never reads the calendar's files")
                (repo / name).write_text("VALUE = 1\n")
            (repo / "ltcm/data/kalshi.py").write_text("VALUE = 2\n")
            equity_fingerprint.cache_clear()
            self.assertEqual(equity_fingerprint(repo), original, "a data source the calendar never imports moves nothing")
            (repo / "ltcm/broker.py").unlink()
            equity_fingerprint.cache_clear()
            with self.assertRaises(OSError):
                equity_fingerprint(repo)  # a release without the calendar has no identity, never a smaller one


class TheFirstDecisionsWindow(unittest.TestCase):
    """evidence-4: the Gym's first decision of every run saw `history` rows where a live decision sees `history` + 1.
    The store sliced `history` sessions before the run's first, the engine decides at the close of the session before
    it, and the ctx then reached back only to the slice's start. The I6 test never draws that session."""

    PROGRAM = ("NEEDS = {'symbols': ['SPY'], 'history': 5, 'max_hold_sessions': 2}\nPARAMS = {}\n\n\n"
               "def decide(ctx):\n"
               "    close = ctx.bars['SPY'].close\n"
               "    oldest = float(close[-6])  # history 5: the session and the five before it\n"
               "    if ctx.positions or oldest <= 0:\n        return []\n"
               "    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open', 'tag': 'first'}]\n")

    @classmethod
    def setUpClass(cls):
        import datetime as dt
        import tempfile

        from league.equity import synth

        cls.dir = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_store(cls.dir.name, symbols=("SPY", "QQQ"), start=dt.date(2024, 6, 3),
                                         end=dt.date(2025, 6, 30), seed=5,
                                         dividends={"SPY": [(dt.date(2025, 3, 21), 1.5)]})

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_the_first_decision_reads_the_rows_a_live_decision_reads(self):
        from league.equity import ctx as C
        from league.equity import synth
        from league.equity.program import Needs
        from league.equity.store import EquityStore

        for history in (0, 1, 5, 30):
            with self.subTest(history=history):
                needs = Needs(("SPY", "QQQ"), history, 20)
                bars = EquityStore(self.root).bars(needs.symbols, "validation", history=history)
                self.assertEqual(bars.first, history + 1)
                t = bars.first - 1  # the engine's first decision: the close of the session before the run's first
                common = dict(needs=needs, cash=1000.0, equity=1000.0, budget=1000.0, caps={"SPY": 500.0, "QQQ": 500.0},
                              params={})
                gym = C.inputs_from_bars(bars, t, **common)
                self.assertEqual(len(gym.days), history + 1, "the session and `history` before it")
                live = C.inputs_from_fetch({s: synth.bar_rows(bars, s, t, adjustment="raw") for s in needs.symbols},
                                           {s: synth.bar_rows(bars, s, t, adjustment="all") for s in needs.symbols},
                                           day=bars.day(t).isoformat(), **common)
                self.assertEqual(C.ctx_bytes(C.build(live)), C.ctx_bytes(C.build(gym)), "I6 at the first decision")

    def test_a_program_that_reads_its_whole_history_trades_the_windows_first_session(self):
        import datetime as dt

        from league.equity.runner import run_bars
        from league.equity.store import EquityStore

        bars = EquityStore(self.root).bars(["SPY"], "validation", history=5)
        result = run_bars(self.PROGRAM, None, bars, name="whole-history")
        self.assertEqual((result["status"], result["runtime"]["errors"]), ("ok", 0), "no IndexError at the first decision")
        self.assertEqual(min(lot["entry_day"] for lot in result["lots"]), dt.date(2025, 1, 2).isoformat(),
                         "it trades the window's first session, as it would live")

    def test_a_store_that_starts_at_the_runs_first_session_gives_what_it_has(self):
        import datetime as dt

        from league.equity.store import EquityStore

        bars = EquityStore(self.root).bars(["SPY"], "train", history=5)
        self.assertEqual((bars.first, bars.day(0)), (0, dt.date(2024, 6, 3)), "nothing before the store's first day")


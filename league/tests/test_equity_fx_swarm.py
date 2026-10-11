"""Release E1's review fixes on the swarm, evidence, ops and docs side (the adversarial review of feat/equity-e1, Oct 10,
2026; findings by id in each test's docstring). One file, so the four fixers' branches never meet in a test file.

The swarm tests run on league/tests/test_elane_gate.py's harness (the runner and the screen faked at their interfaces);
the `World` cases run the real things on a SYNTHETIC store (league/equity/synth.py; never market data): the real
SwarmStore, Tournament and Gate, `runner.Isolated` over an `InlineDecider`, the real screen under the FAKE receipt 2."""

from __future__ import annotations

import json
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
    """`FakeRunner` whose Train-era runs fail for the families named in `broken`."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.broken: set[str] = set()

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

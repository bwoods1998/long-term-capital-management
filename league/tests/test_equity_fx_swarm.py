"""Release E1's review fixes on the swarm, evidence, ops and docs side (the adversarial review of feat/equity-e1, Oct 10,
2026; findings by id in each test's docstring). One file, so the four fixers' branches never meet in a test file.

The swarm tests run on league/tests/test_elane_gate.py's harness (the runner and the screen faked at their interfaces);
the `World` cases run the real things on a SYNTHETIC store (league/equity/synth.py; never market data): the real
SwarmStore, Tournament and Gate, `runner.Isolated` over an `InlineDecider`, the real screen under the FAKE receipt 2."""

from __future__ import annotations

from unittest import mock

from league.equity import BETA, EQUITY_ENGINE_VERSION
from league.equity import screen as S
from league.swarm import elane
from league.swarm.evaluator import EQUITY_SELECTION_KEYS, adopt_equity
from league.swarm.gate import run_sha
from league.tests.test_elane import CODE, ON
from league.tests.test_elane_gate import EquityCase, FakeRunner, screen

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

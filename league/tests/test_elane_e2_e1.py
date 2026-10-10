"""Release E2 ON E1'S OWN CODE (league/swarm/ELANE_E2_PATCHES.md): the guard E1's tournament applies (patch 5) inside E1's
real `Tournament.equity_round`; E1's look reads E2's review (`elane.reviewed`); E1's equity adoption and E2's upkeep;
E1's lane-scoped graveyard binding the equity births; the options population's floor (patch 9) and the operator's stall
facts (patch 10) left unmasked by the equity lanes. Skipped on a tree without E1's equity lanes (the E2 branch's own
skeleton); it runs once E2 is merged into E1 with its patches. Every family, program and number here is invented."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.swarm import elane, elane_train
from league.tests import elane_e2_fakes as fx

E1 = callable(getattr(elane, "next_try", None)) and callable(getattr(elane, "reviewed", None))
SETTINGS = {"elane": {"mode": "gate", "universe": ["SPY", "QQQ", "IWM", "DIA"], "structures": ["etf"],
                      "birth_share": 0.25, "e2": {"train_budget": 3, "train_per_round": 5}},
            "population": {"start": 48, "ceiling": 96, "floor": 2}, "architect": {}, "gym": {}}


@unittest.skipUnless(E1, "E1's equity lanes are not in this tree (the E2 branch's skeleton)")
class OnE1(unittest.TestCase):
    def setUp(self):
        from league.swarm.elane_train import EquityResearcher

        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.reviews: list = []
        self.router = fx.FakeRouter(self.script)
        self.runner = fx.FakeRunner()
        self.researcher = EquityResearcher(self.store, self.router, SETTINGS, runner=self.runner, clock=self.clock)
        self.validated: list = []

    def script(self, call):
        if fx.is_review(call):
            return self.reviews.pop(0) if self.reviews else fx.review_answer("pass", model=call["sail_profile"])
        return fx.answer([])

    def round(self) -> dict:
        """E1's real `Tournament.equity_round` (with patch 5), its `elane.validate` recorded instead of run."""
        from league.swarm.tournament import Tournament

        def validate(t, fam, version):
            self.validated.append((fam["id"], version["n"]))
            return {"version": version["n"], "passed": False, "entered": False}
        with mock.patch.object(elane, "validate", validate):
            return Tournament.equity_round(SimpleNamespace(store=self.store, settings=SETTINGS))

    def test_patch_5_validates_only_the_pass_and_a_stale_one_again(self):
        from league.swarm.gate import run_sha

        fam = fx.e2_family(self.store, "e2-new", code=fx.program())
        self.assertEqual(elane.next_try(self.store, fam, SETTINGS), 1, "E1 alone would spend the try on an untrained v1")
        self.round()
        self.assertEqual(self.validated, [], "patch 5: no try before the Train pass and the review")
        self.researcher.run()
        fam = self.store.family("e2-new")
        self.assertTrue(elane.reviewed(fam["state"], run_sha(self.store.version("e2-new", 1))), "E1's look reads it")
        self.round()
        self.assertEqual(self.validated, [("e2-new", 1)])
        # What E1's `validate` records, then the look finds the recorded run did not reproduce (a daily refetch).
        self.store.add_run("e2-new", 1, {"run_id": "val-1", "status": "ok", "trials": 1, "summary": {}},
                           window="validation", stress=1.0, purpose="validation")
        self.store.update_family("e2-new", validated_version=1)
        self.store.set_state("e2-new", validation_version=1, gate_ready=False,
                             **{elane.TRY_KEY: {"version": 1, "entered": True, "precheck": True},
                                elane.VERDICTS_KEY: {"1": {"entered": True, "stale": True}}})
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("e2-new"), SETTINGS))
        self.round()
        self.assertEqual(self.validated, [("e2-new", 1), ("e2-new", 1)], "the stale verdict is validated again")

    def test_e1s_adoption_then_e2s_upkeep_restore_the_review(self):
        from league.swarm import evaluator
        from league.swarm.gate import run_sha

        ident = {"now": {"equity": "a" * 64, "engine": "equity-engine-1"}}
        with mock.patch.object(evaluator, "equity_identity", lambda: dict(ident["now"])):
            fx.e2_family(self.store, "e2-adopt", code=fx.program(share=0.4))
            self.researcher.run()
            ident["now"] = {"equity": "b" * 64, "engine": "equity-engine-1"}
            evaluator.adopt_equity(self.store, ident["now"])
            fam = self.store.family("e2-adopt")
            sha = run_sha(self.store.version("e2-adopt", 1))
            self.assertFalse(elane.reviewed(fam["state"], sha), "E1's adoption clears the review with the selection keys")
            self.assertIsNone(fam["best_version"])
            self.round()
            self.assertEqual(self.validated, [], "a stale pass is not validated")
            self.researcher.run()  # the pass is Train-scored again under the new identity
            self.researcher.run()  # the upkeep restores the review and the best version
            fam = self.store.family("e2-adopt")
            self.assertTrue(elane.reviewed(fam["state"], sha))
            self.assertEqual(fam["best_version"], 1)
            self.round()
            self.assertEqual(self.validated, [("e2-adopt", 1)])

    def test_e1s_graveyard_binds_its_own_lane_only(self):
        from league.swarm import cards
        from league.swarm.architect import Architect
        from league.swarm.elane_births import LAST_KEY

        dead = fx.e2_family(self.store, "dead-qqq", lane="equity", agenda="reversal", symbols=("QQQ",),
                            mechanism="Invented reversal idea on QQQ, refuted on Train.",
                            record={"status": "refuted", "versions": {"1": {"fails": ["Y2"]}},
                                    "refuted": {"at": "2026-10-10T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        cards.put(self.store, dead["id"], fx.card("equity", ("QQQ",)), "etf")
        self.store.bury(dead["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        self.store.retire(dead["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        answers = [fx.answer([fx.proposal("eq-again", lane="equity", agenda="reversal", symbols=("IWM",),
                                          code=fx.program("IWM")),
                              fx.proposal("beta-free", lane="beta", agenda="overnight", symbols=("DIA",),
                                          code=fx.program("DIA"))])]
        router = fx.FakeRouter(lambda call: answers.pop(0) if answers else fx.answer([]))
        for i in range(30):
            self.store.event("swarm.born", f"opt-{i}", {"structure": "debit_vertical", "roots": ["SPY"]})
        out = Architect(self.store, router, SETTINGS, clock=self.clock).equity_pass()
        self.assertEqual(out["born"], ["beta-free"], json.dumps(self.store.get(LAST_KEY)))
        why = {r["slug"]: r["why"] for r in self.store.get(LAST_KEY)["refused"]}
        self.assertTrue(why["eq-again"].startswith("graveyard:"), why)

    def test_patch_9_the_options_floor_counts_options_only(self):
        for i in range(2):
            self.store.add_family({"id": f"opt-{i}", "mechanism": f"An invented options idea {i}.",
                                   "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        for i in range(5):
            fx.e2_family(self.store, f"eq-{i}", symbols=(["SPY", "QQQ", "IWM", "DIA", "SPY"][i],),
                         mechanism=f"Invented equity idea {i} for the floor.")
        out = self.store.retire_gym("opt-0", "an invented reason", floor=2, source="test")
        self.assertEqual(out.get("deferred"), "population_floor", "five equity families never hold the options floor up")

    def test_patch_10_stall_facts_leave_the_equity_lanes_out(self):
        from league.ops import guard
        from league.ops import stall as ST

        root = Path(self.store.root)
        self.store.add_family({"id": "opt-a", "mechanism": "An invented options idea.", "structure": "debit_vertical",
                               "roots": ["SPY"]}, origin="architect")
        for i in range(3):
            fam = fx.e2_family(self.store, f"eq-{i}", symbols=(["SPY", "QQQ", "IWM"][i],),
                               mechanism=f"Invented equity idea {i} for the alarms.")
            self.store.event("swarm.born", fam["id"], {"lane": "beta", "structure": "etf", "roots": ["SPY"]})
            self.store.add_run(fam["id"], None, fx.train_result(), window="train", stress=1.0, purpose="elane_train")
        facts = guard.read(root / "swarm.sqlite", lambda db: ST.swarm_facts(db, self.clock()))
        self.assertEqual((facts["births"], facts["alive"], facts["gym_runs"]), (0, 1, 0))


if __name__ == "__main__":
    unittest.main()

"""Release E2 ON E1'S OWN CODE (league/swarm/ELANE_E2_PATCHES.md): the guard E1's tournament applies (patch 5) inside E1's
real `Tournament.equity_round`; E1's look reads E2's review (`elane.reviewed`); E1's equity adoption and E2's upkeep;
E1's lane-scoped graveyard binding the equity births; the options population's floor (patch 9) and the operator's stall
facts (patch 10) left unmasked by the equity lanes; and A15's restart check on E1's own isolated runner, decider kinds
and ctx builder (a stateless program and a cache pass, a session counter fails STATE; the ctx stream holds the run's own
lots). Skipped on a tree without E1's equity lanes (the E2 branch's own skeleton); it runs once E2 is merged into E1 with
its patches. Every family, program and number here is invented (the market is E1's synthetic store)."""

from __future__ import annotations

import datetime as dt
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
        # The fake runner's runs carry no bars: the restart check reads the invented ctx stream (StateOnE1: E1's own).
        patcher = mock.patch.object(elane_train, "state_inputs", fx.state_inputs)
        patcher.start()
        self.addCleanup(patcher.stop)
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


@unittest.skipUnless(E1, "E1's equity lanes are not in this tree (the E2 branch's skeleton)")
class StateOnE1(unittest.TestCase):
    """A15 on E1's own code: E1's isolated runner over its synthetic store (invented prices), its decider kinds in this
    process (`InlineDecider`: a load is a fresh STATE, as in the child) and in a real child (`Decider`), and E2's ctx
    stream built by E1's ctx builder from each run's own bars, lots and daily record."""

    SPANS = ((dt.date(2016, 1, 4), dt.date(2016, 6, 30)), (dt.date(2022, 1, 3), dt.date(2022, 4, 29)))

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        cls.store_root = synth.synthetic_store(Path(cls.tmp.name) / "plain" / elane.STORE_DIR, symbols=("SPY",),
                                               end=dt.date(2024, 12, 31), seed=5, drift=0.05, vol=0.15)
        # An invented market that pays the overnight hold every year, so the stateless program meets Y1-R1 and the
        # researcher's own score reaches the restart check.
        cls.paying_root = synth.synthetic_store(Path(cls.tmp.name) / "paying" / elane.STORE_DIR, symbols=("SPY",),
                                                end=dt.date(2024, 12, 31), seed=5, drift=0.8, vol=0.04)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def runner(self, root=None, decider=None):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        return Isolated(decider if decider is not None else InlineDecider(), root or self.store_root)

    def check(self, code: str) -> tuple[list, dict]:
        runner = self.runner()
        runs = [runner.train(code, {}, name="p", start=first, end=last, k=1.0) for first, last in self.SPANS]
        for run, span in zip(runs, self.SPANS):
            self.assertEqual(run.result["status"], "ok")
            self.assertEqual(elane_train.outside_years(run.result, spans=[span]), [], "inside its own span")
        out = elane_train.restart_check(runner.decider, code, {}, name="p",
                                        streams=[elane_train.state_inputs(run) for run in runs])
        self.assertEqual(runner.decider.kind_loaded, {}, "every instance dropped")
        return runs, out

    def test_the_train_spans_are_inside_e1s_train_window_and_its_runner_cuts_to_them(self):
        from league.equity import config

        first, last = config.WINDOWS["train"]
        for start, end in elane_train.TRAIN_SPANS:
            self.assertTrue(first <= start <= end <= last)
        self.assertEqual(elane_train.TRAIN_SPANS, config.TRAIN_ERA_SEGMENTS, "the spans E1's screen floor also reads")
        runner = self.runner()
        for span in elane_train.TRAIN_SPANS:
            run = runner.train(fx.program(), {}, name="p", start=span[0], end=span[1], k=1.0)
            days = [row[0] for row in run.result["daily"]]
            self.assertTrue(span[0].isoformat() <= days[0] <= days[-1] <= span[1].isoformat())
            self.assertEqual(elane_train.outside_years(run.result, spans=[span]), [])
            self.assertFalse({d[:4] for d in days} & {str(y) for y in elane_train.RESERVE_YEARS}, "no reserve session")
        # E1's whole Train window holds the reserve years: a run over it is refused whole, as E2 never asks for one.
        whole = runner.train(fx.program(), {}, name="p", start=first, end=last, k=1.0)
        self.assertTrue({"2020", "2021"} <= set(elane_train.outside_years(whole.result)))
        self.assertEqual(elane_train.train_score(whole.result, whole.result)["fails"], ["WINDOW"])

    def test_a_stateless_program_and_a_cache_pass_and_a_session_counter_fails(self):
        runs, out = self.check(fx.program())
        decisions = sum(run.bars.n - max(run.bars.first - 1, 0) - 1 for run in runs)
        self.assertEqual((out["sessions"], out["matched"], out["held"]), (decisions, decisions, True))
        _, out = self.check(fx.CACHE)
        self.assertEqual((out["matched"], out["held"], out["disqualified"]), (out["sessions"], True, 0))
        _, out = self.check(fx.COUNTER)
        self.assertFalse(out["held"], out)
        self.assertLess(out["share"], elane_train.BAR["state_match"])
        self.assertEqual(out["first_miss"]["after_reset"], 0, "the first session after the first reset")

    def test_the_ctx_stream_holds_the_runs_own_lots(self):
        """The stateless program sells every lot it holds at the open: on the stream, the lots it names at each close
        are exactly the lots the engine sold at the next open (the stream's positions are the run's)."""
        from league.live.decider import InlineDecider

        runs, _ = self.check(fx.program())
        decider = InlineDecider()
        decider.kind_load("equity", "probe", {"code": fx.program(), "params": {}, "name": "p"})
        for run in runs:
            days = {lot["exit_day"]: set() for lot in run.result["lots"] if lot["reason"] == "program"}
            for lot in run.result["lots"]:
                if lot["reason"] == "program":
                    days[lot["exit_day"]].add(lot["lid"])
            named = {}
            stream = elane_train.state_inputs(run)
            for j, inputs in zip(range(max(run.bars.first - 1, 0), run.bars.n - 1), stream):
                answer = decider.kind("equity", "decide", {"jobs": [{"key": "probe", "inputs": inputs}]})
                sells = {i["sell"] for i in answer["results"]["probe"]["intents"] if "sell" in i}
                if sells:
                    named[run.bars.day(j + 1).isoformat()] = sells
            self.assertTrue(days)
            self.assertEqual(named, days)

    def test_a_result_that_does_not_fit_its_bars_stops_the_check(self):
        runner = self.runner()
        run = runner.train(fx.program(), {}, name="p", start=self.SPANS[0][0], end=self.SPANS[0][1], k=1.0)
        short = SimpleNamespace(result={**run.result, "daily": run.result["daily"][:-1]}, bars=run.bars)
        moved = SimpleNamespace(result={**run.result, "lots": [{**run.result["lots"][0], "entry_day": "2021-03-01"}]},
                                bars=run.bars)
        for bad in (short, moved, SimpleNamespace(result=run.result, bars=None)):
            with self.assertRaises(elane_train.StateCheckInterrupted):
                list(elane_train.state_inputs(bad))

    def test_a_child_that_died_between_two_requests_is_caught_on_e1s_decider(self):
        """E1's real decider child: killed between two requests, it is started again and E1 reloads its instances with
        fresh memory (at E1's 4baf7c10 without counting a restart: `Decider._ask` counts only a request that failed).
        The check catches it either way, by the instance's call count or by `restarts`: the House's, never a pass."""
        import os
        import signal
        import sys

        from league.live.decider import Decider

        decider = Decider(python=sys.executable, allow_unisolated=True)
        self.addCleanup(decider.close)
        runner = self.runner(decider=decider)
        code = fx.COUNTER
        run = runner.train(code, {}, name="p", start=self.SPANS[0][0], end=self.SPANS[0][1], k=1.0)
        whole = elane_train.restart_check(decider, code, {}, name="p", streams=[elane_train.state_inputs(run)])
        self.assertFalse(whole["held"], "the counter fails STATE in the real child too")
        self.assertEqual(whole["sessions"], run.bars.n - max(run.bars.first - 1, 0) - 1)

        def killed(after: int):
            for i, inputs in enumerate(elane_train.state_inputs(run)):
                if i == after:
                    proc = decider.proc
                    os.kill(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=30)
                    for stream in (proc.stdin, proc.stdout):
                        stream.close()
                yield inputs
        with self.assertRaises(elane_train.StateCheckInterrupted) as caught:
            elane_train.restart_check(decider, code, {}, name="p", streams=[killed(27)])
        self.assertRegex(str(caught.exception), "reloaded an instance|restarted during the restart check")
        self.assertEqual(decider.kind_loaded, {}, "every instance dropped")
        # The child is sound again: the next check finishes.
        again = elane_train.restart_check(decider, code, {}, name="p", streams=[elane_train.state_inputs(run)])
        self.assertEqual((again["sessions"], again["matched"]), (whole["sessions"], whole["matched"]))

    def test_a_version_is_judged_over_both_train_spans_on_e1s_runner(self):
        from league.swarm.elane_train import EquityResearcher

        clock = fx.Clock()
        store = fx.new_store(self, clock)
        router = fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                               else fx.answer([]))
        fam = fx.e2_family(store, "e1-state", code=fx.program())
        runner = self.runner(self.paying_root)
        out = EquityResearcher(store, router, SETTINGS, runner=runner, clock=clock).score(fam, store.version(fam["id"], 1))
        rec = elane_train.record_of(store.family(fam["id"]))
        v1 = rec["versions"]["1"]
        self.assertEqual((v1["fails"], v1["passed"], rec["passed_version"]), ([], True, 1), out)
        self.assertEqual(sorted(v1["years"]), [str(y) for y in elane_train.TRAIN_YEARS], "the seven Train years, no other")
        self.assertEqual((v1["state"]["matched"], v1["state"]["disqualified"]), (v1["state"]["sessions"], 0),
                         "a stateless program keeps its intents")
        runs = store.runs(fam["id"], window="train")
        self.assertEqual(sorted(r["stress"] for r in runs), [1.0, 1.0, 1.5, 1.5])
        days = sum(int(r["summary"]["days"]) for r in runs if r["stress"] == 1.0)
        self.assertEqual(v1["state"]["sessions"], days - 1, "every decision session of both spans (none before 2016's "
                                                             "first session: the store starts there)")
        self.assertEqual(runner.decider.kind_loaded, {})
        # A program that keeps its clock in STATE earns the same way on this market and meets Y1-R1: STATE alone fails it.
        counter = fx.COUNTER.replace('"every": 7', '"every": 3')
        fam = fx.e2_family(store, "e1-counter", code=counter, symbols=("SPY",))
        EquityResearcher(store, router, SETTINGS, runner=runner, clock=clock).score(fam, store.version(fam["id"], 1))
        rec = elane_train.record_of(store.family(fam["id"]))
        v1 = rec["versions"]["1"]
        self.assertEqual((v1["fails"], v1["passed"], rec.get("passed_version")), (["STATE"], False, None))
        self.assertGreaterEqual(v1["active_years"], elane_train.BAR["min_active_years"])
        self.assertGreater(v1["pnl_15"], 0, "it met the rest of the bar")
        self.assertLess(v1["state"]["share"], elane_train.BAR["state_match"])
        self.assertFalse(elane_train.may_validate(store, store.family(fam["id"]), 1))


if __name__ == "__main__":
    unittest.main()

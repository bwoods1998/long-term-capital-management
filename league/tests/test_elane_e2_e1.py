"""Release E2 ON E1'S OWN CODE (league/swarm/ELANE_E2_PATCHES.md): the guard E1's tournament applies (patch 5) inside E1's
real `Tournament.equity_round`; E1's look reads E2's review (`elane.reviewed`); E1's equity adoption and E2's upkeep;
E1's lane-scoped graveyard binding the equity births; the options population's floor (patch 9) and the operator's stall
facts (patch 10) left unmasked by the equity lanes; and A15's restart check on E1's own isolated runner, decider kinds
and ctx builder (a stateless program and a cache pass; a session counter fails STATE whatever its period, with the
clocks of 5, 10 and 20 sessions the A15 review found passing; a decide that fails on an empty STATE; a cache updated in
place, which passes on rounding alone and fails once dividends re-base ctx's history; the ctx stream holds the run's own
lots); and what of the reserve reaches Train on E1's runner (its bars, as look-back). Skipped on a tree without E1's
equity lanes (the E2 branch's own skeleton); it runs once E2 is merged into E1 with its patches. Every family, program
and number here is invented (the market is E1's synthetic store)."""

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
        # The plain market with invented dividends inside both short spans: ctx's adjusted history is re-based at each.
        cls.dividend_root = synth.synthetic_store(
            Path(cls.tmp.name) / "dividends" / elane.STORE_DIR, symbols=("SPY",), end=dt.date(2024, 12, 31), seed=5,
            drift=0.05, vol=0.15, dividends={"SPY": [(dt.date(2016, 2, 16), 1.2), (dt.date(2016, 4, 15), 1.2),
                                                     (dt.date(2022, 2, 15), 1.2), (dt.date(2022, 3, 15), 1.2)]})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def runner(self, root=None, decider=None):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        return Isolated(decider if decider is not None else InlineDecider(), root or self.store_root)

    def check(self, code: str, root=None) -> tuple[list, dict]:
        runner = self.runner(root)
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
        self.assertEqual(out["first_miss"]["after_reset"], 0, "the first session after a reset")

    def test_a_clock_whose_period_divides_the_reset_period_fails_on_e1s_runner(self):
        """The A15 review's first finding, on E1's runner: clocks of 2, 4, 5, 10 and 20 sessions kept in STATE matched
        on every session while B's resets were counted from the span's first session."""
        for period in (2, 4, 5, 10, 20):
            runs, out = self.check(fx.counter(period))
            self.assertFalse(out["held"], (period, out))
            self.assertLess(out["share"], 0.95, period)
            # The resets counted from the span's start (the schedule the review found): blind to this clock.
            runner = self.runner()
            old = elane_train.restart_check(runner.decider, fx.counter(period), {}, name="p", first=0,
                                            streams=[elane_train.state_inputs(run) for run in runs])
            self.assertEqual(old["matched"], old["sessions"], period)

    def test_a_decide_that_fails_on_an_empty_state_is_no_match_on_e1s_runner(self):
        """The A15 review's second finding, on E1's runner and its `stats.errors`: the trailing-peak program runs clean
        uninterrupted (no error in its Train runs) and raises once STATE is emptied under a held lot."""
        runs, out = self.check(fx.PEAK)
        self.assertEqual([run.result["runtime"]["errors"] for run in runs], [0, 0], "its Train runs never fail")
        self.assertGreater(out["failed"], 0.01 * out["sessions"])
        self.assertEqual((out["held"], out["disqualified"]), (False, 0), out)
        self.assertLessEqual(out["matched"], out["sessions"] - out["failed"])
        self.assertIn("the decide failed", elane_train.restart_text({"state": out}))

    def test_a_cache_updated_in_place_on_e1s_runner(self):
        """The A15 review's third finding. With no dividend ctx's history never moves: the in-place sum is the value ctx
        gives, in another order of addition, and passes (compared to the last digit it failed). With dividends ctx's
        adjusted history is re-based and rounded at each: the carried sum is no longer what ctx gives, the sizes differ
        past the sixth place, and it fails STATE with the sessions and the gap told; its recomputing twin passes."""
        # The fakes' programs, sized for this market's variance (a buy's share stays under one, so its size shows).
        inplace, recomputed = (code.replace('"target": 0.0002', '"target": 0.00002') for code in (fx.INPLACE, fx.RECOMPUTED))
        runs, out = self.check(inplace)
        self.assertEqual((out["matched"], out["held"], out["sized"]), (out["sessions"], True, 0), out)
        with mock.patch.dict(elane_train.SIZE_TOL, {"share": 0.0}):
            runner = self.runner()
            exact = elane_train.restart_check(runner.decider, inplace, {}, name="p",
                                              streams=[elane_train.state_inputs(run) for run in runs])
        self.assertFalse(exact["held"], "compared to the last digit, rounding alone failed it")
        self.assertGreater(exact["sized"], 0.05 * exact["sessions"])
        self.assertLess(exact["size_gap"]["share"], 1e-12)
        _, out = self.check(inplace, self.dividend_root)
        self.assertFalse(out["held"], out)
        self.assertGreater(out["sized"], 0.05 * out["sessions"])
        self.assertEqual(out["sized"], out["sessions"] - out["matched"], "the sizes are all that differed")
        self.assertGreater(out["size_gap"]["share"], elane_train.SIZE_TOL["share"])
        self.assertLess(out["size_gap"]["share"], 0.01, "a drift, not another order")
        self.assertIn("differed only in a buy's size", elane_train.restart_text({"state": out}))
        for root in (None, self.dividend_root):
            _, out = self.check(recomputed, root)
            self.assertEqual((out["matched"], out["held"]), (out["sessions"], True), out)

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
        # A weekly clock (5 sessions, a period that divides the check's 20) was the A15 review's first finding: it met
        # the whole bar and became the lineage's Validation try. So was the program whose decide fails on an empty STATE.
        for slug, code in (("e1-counter-3", fx.counter(3)), ("e1-counter-5", fx.counter(5)),
                           ("e1-peak", fx.PEAK.replace('"max_hold_sessions": 3', '"max_hold_sessions": 2'))):
            fam = fx.e2_family(store, slug, code=code, symbols=("SPY",), mechanism=f"Invented idea {slug} on the index.")
            EquityResearcher(store, router, SETTINGS, runner=runner, clock=clock).score(fam, store.version(fam["id"], 1))
            rec = elane_train.record_of(store.family(fam["id"]))
            v1 = rec["versions"]["1"]
            self.assertEqual((v1["fails"], v1["passed"], rec.get("passed_version")), (["STATE"], False, None), slug)
            self.assertGreaterEqual(v1["active_years"], elane_train.BAR["min_active_years"])
            self.assertGreater(v1["pnl_15"], 0, "it met the rest of the bar")
            self.assertLess(v1["state"]["share"], elane_train.BAR["state_match"])
            self.assertFalse(elane_train.may_validate(store, store.family(fam["id"]), 1))
        self.assertGreater(v1["state"]["failed"], 0, "the peak program's decide failed in the reset run alone")


class ReserveMoved:
    """E1's decider with the reserve's bars moved in every run it is sent: each 2020-2021 row of the slice has its
    prices scaled by a smooth bump over the two years (one at both ends, `1 + bump` in the middle), so the market is the
    same on every Train session and differs only inside the reserve. `moved`: the reserve rows of each run's slice; `last`: the latest reserve day of
    each (None for none)."""

    def __init__(self, inner, bump: float):
        self.inner, self.bump, self.moved, self.last = inner, float(bump), [], []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def kind(self, kind, op, payload, **kw):
        if op == "run":
            payload = {**payload, "bars": self.market(payload["bars"])}
        return self.inner.kind(kind, op, payload, **kw)

    def market(self, bars):
        import dataclasses
        import math

        import numpy as np

        from league.equity.store import from_ordinal

        first, last = dt.date(2020, 1, 1).toordinal(), dt.date(2022, 1, 1).toordinal()
        days = [from_ordinal(int(d)) for d in bars.days]
        rows = np.array([d.year in elane_train.RESERVE_YEARS for d in days])
        assert not rows[bars.first:].any(), "no run session is a reserve session"
        self.moved.append(int(rows.sum()))
        self.last.append(max((d for d in days if d.year in elane_train.RESERVE_YEARS), default=None))
        factor = np.array([1.0 + self.bump * math.sin(math.pi * (d.toordinal() - first) / (last - first)) ** 2
                           if d.year in elane_train.RESERVE_YEARS else 1.0 for d in days])
        raw = {sym: a.copy() for sym, a in bars.raw.items()}
        adj = {sym: a.copy() for sym, a in bars.adj.items()}
        for sym in raw:
            raw[sym][:, :4] *= factor[:, None]
            adj[sym][:, :4] *= factor[:, None]
        return dataclasses.replace(bars, raw=raw, adj=adj)


#: An invented trend program with a 126-session look-back: in the first half of 2022 it compares a 2022 close with a
#: reserve close.
TREND = '''import math
import numpy as np

NEEDS = {"symbols": ["SPY"], "history": 252, "max_hold_sessions": 5}
PARAMS = {"look": 126, "share": 0.5}


def decide(ctx):
    close = ctx.bars["SPY"].close
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions if lot["held_sessions"] >= 3]
    look = ctx.params["look"]
    if len(close) > look and close[-1] > close[-1 - look] and not ctx.positions:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
'''


@unittest.skipUnless(E1, "E1's equity lanes are not in this tree (the E2 branch's skeleton)")
class ReserveOnE1(unittest.TestCase):
    """THE RESERVE on E1's runner (the A15 review's fourth finding): what holds, and what does not. E2 runs no reserve
    session and keeps no reserve row; the reserve's BARS still reach the 2022-2024 Train figures (E1's runner hands the
    run its NEEDS `history` + 1 sessions before 2022-01-03: the engine's first decision is at the close of the session
    before the run's first, E1's `store._slice`). So EVERY program's 2022-2024 run reads the last 2021 session, a
    program with no look-back too, and one with look-back reads `history` more. Two markets that differ only in
    2020-2021: a program that asks for no history and holds no price against another has the same figures of its own
    (the buy-and-hold reported beside its 2022 moves with the last 2021 close), and one with look-back is the same in
    2016-2019 and differs from 2022 on."""

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_store(Path(cls.tmp.name) / "plain" / elane.STORE_DIR, symbols=("SPY",),
                                         end=dt.date(2024, 12, 31), seed=5, drift=0.05, vol=0.15)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def verdict(self, code: str, bump: float | None) -> tuple[dict, list[int]]:
        """The verdict E2 keeps of `code` (its Train figures: `train_score` of the summed spans) in the market as it is
        (`bump` None) or with the reserve moved, and the reserve rows each run's slice held (`self.last`: the latest
        reserve day of each)."""
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        decider = ReserveMoved(InlineDecider(), bump or 0.0)
        runner = Isolated(decider, self.root)
        parts = {k: [runner.train(code, {}, name="p", start=first, end=last, k=k).result
                     for first, last in elane_train.TRAIN_SPANS] for k in (1.0, 1.5)}
        for results in parts.values():
            for result, span in zip(results, elane_train.TRAIN_SPANS):
                self.assertEqual(elane_train.outside_years(result, spans=[span]), [], "no reserve row, day or figure")
                self.assertFalse({row[0][:4] for row in result["daily"]} & {"2020", "2021"}, "no reserve session")
        self.last = decider.last
        return elane_train.train_score(elane_train.combine(parts[1.0]), elane_train.combine(parts[1.5])), decider.moved

    def test_a_program_that_asks_for_no_history_reads_the_last_reserve_session_alone(self):
        # E1's slice is `history` + 1 sessions before the run's first (the first decision's own session): with no
        # look-back at all, each 2022-2024 run still holds ONE reserve bar, the last 2021 session, and its first
        # decision reads it. This program holds no price against another, so the two markets give it the same figures
        # of its own; the same-exposure buy-and-hold reported BESIDE its 2022 is measured from that close and moves.
        code = fx.program().replace('"history": 2', '"history": 0')
        as_is, held = self.verdict(code, None)
        moved, held_moved = self.verdict(code, 2.0)
        self.assertEqual((held, held_moved), ([0, 1, 0, 1], [0, 1, 0, 1]),
                         "each 2022-2024 slice holds one reserve bar (history + 1), the 2016-2019 slices none")
        days = [d for d in self.last if d is not None]
        self.assertEqual(len(days), 2)
        self.assertEqual({(d.year, d.month) for d in days}, {(2021, 12)}, "the last 2021 session")
        self.assertTrue(all(d >= dt.date(2021, 12, 27) for d in days), days)
        self.assertTrue(as_is["years"] and as_is["summary"]["trades"], "really run")

        def own(verdict: dict) -> str:
            """The verdict less the buy-and-hold reported beside it (never a bar)."""
            out = json.loads(json.dumps(verdict))
            out["beside"].pop("bh_pnl")
            out["beside"].pop("drift_share")
            out["years"]["2022"].pop("bh_pnl")
            return json.dumps(out, sort_keys=True)
        self.assertEqual(own(as_is), own(moved), "its own lots, P&L, t and fails, and every other year's row")
        self.assertNotEqual(as_is["years"]["2022"]["bh_pnl"], moved["years"]["2022"]["bh_pnl"],
                            "the buy-and-hold beside its 2022 starts from the last 2021 close")
        self.assertEqual({y: r["bh_pnl"] for y, r in as_is["years"].items() if y != "2022"},
                         {y: r["bh_pnl"] for y, r in moved["years"].items() if y != "2022"})

    def test_a_program_with_look_back_reads_the_reserves_bars_in_2022(self):
        as_is, held = self.verdict(TREND, None)
        moved, held_moved = self.verdict(TREND, 2.0)
        # Each 2022-2024 run's slice holds the 252 + 1 sessions before 2022-01-03 (reserve bars: NEEDS `history` and the
        # first decision's own session); the 2016-2019 runs' none.
        self.assertEqual((held, held_moved), ([0, 253, 0, 253], [0, 253, 0, 253]))
        early = ("2016", "2017", "2018", "2019")
        self.assertEqual(sorted(as_is["years"]), [str(y) for y in elane_train.TRAIN_YEARS], "the seven Train years only")
        self.assertEqual({y: as_is["years"][y] for y in early}, {y: moved["years"][y] for y in early},
                         "2016-2019 is the same market: the same rows")
        self.assertNotEqual(as_is["years"]["2022"], moved["years"]["2022"],
                            "the 2022 row is a function of reserve bars, through the look-back")
        self.assertNotEqual((as_is["pnl_10"], as_is["score"]), (moved["pnl_10"], moved["score"]),
                            "and so are the sums and the pooled t it enters")


if __name__ == "__main__":
    unittest.main()

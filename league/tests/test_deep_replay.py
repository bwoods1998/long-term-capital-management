"""Deep replay: folds never see their future or the holdout; the holdout is sealed and rationed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from league.deep_replay import HOLDOUT, HoldoutSeal, SealedData, StoreClient, fold_tape, folds, version_of
from league.history import HistoryStore
from league.ledger import Ledger
from league.tapes import TapeError, parse_time
from league.tests.test_history import FakeAlpaca, _ingestor


NEEDS = {"venue": "alpaca", "horizon": "day", "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 20}}


class FoldTest(unittest.TestCase):
    def test_folds_are_chronological_contiguous_and_end_by_the_holdout(self):
        out = folds("2016-01-01", horizon="day")
        self.assertGreater(len(out), 20)
        for (a, b), (c, d) in zip(out, out[1:]):
            self.assertEqual(b, c)
            self.assertLess(a, b)
        self.assertEqual(out[-1][1], HOLDOUT[0])
        self.assertEqual(folds("2016-01-01", horizon="hour", count=3)[-1][1], HOLDOUT[0])
        self.assertEqual(len(folds("2016-01-01", horizon="hour", count=3)), 3)


class StoreTapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = HistoryStore.at_root(cls.tmp.name)
        ing = _ingestor(cls.store, FakeAlpaca(), workers=4)
        ing.run(ing.plan(["SPY"], ["1Day", "5Min"], "2025-06-01", "2026-06-01", five_minute=("SPY",)))

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_a_fold_tape_never_holds_a_bar_after_its_end(self):
        tape = fold_tape(self.store, NEEDS, "2025-08-01", "2025-09-01")
        end = parse_time("2025-09-01T00:00:00Z")
        self.assertTrue(tape["steps"])
        for step in tape["steps"]:
            self.assertLessEqual(parse_time(step["t"]), end)
            for bars in (step.get("history_bars") or {}).values():
                for bar in bars:
                    self.assertLessEqual(parse_time(bar["t"]), parse_time(step["t"]))  # available only once closed
        self.assertTrue(tape["warmup_bars"]["SPY"])
        self.assertTrue(all(parse_time(b["t"]) < parse_time("2025-08-01T00:00:00Z") for b in tape["warmup_bars"]["SPY"]))
        self.assertIn("adjusted", tape["source"]["adjustment"])

    def test_execution_bars_are_scaled_into_the_signal_bars_price_space(self):
        tape = fold_tape(self.store, NEEDS, "2025-08-01", "2025-08-08")
        step = next(s for s in tape["steps"] if s.get("execution_bars"))
        raw = self.store.bars("SPY", "5Min", parse_time(step["t"]) - 300, parse_time(step["t"]) - 299, feed="sip", adjustment="raw")[0]
        self.assertAlmostEqual(step["execution_bars"]["SPY"]["o"], raw["o"] * self._factor(raw["t"]), places=6)

    def _factor(self, t):
        from league.deep_replay import _ny_day
        day = _ny_day(t)
        raw = [b for b in self.store.bars("SPY", "1Day", t - 86400 * 3, t + 86400, feed="sip", adjustment="raw") if _ny_day(b["t"]) == day][0]
        adj = [b for b in self.store.bars("SPY", "1Day", t - 86400 * 3, t + 86400, feed="sip", adjustment="all") if _ny_day(b["t"]) == day][0]
        return adj["c"] / raw["c"]

    def test_the_holdout_is_refused_to_development_and_unfetched_history_is_not_a_result(self):
        with self.assertRaises(SealedData):
            fold_tape(self.store, NEEDS, "2025-11-01", "2025-12-01")
        client = StoreClient(self.store)
        with self.assertRaises(SealedData):
            client.request("GET", "https://data.alpaca.markets/v2/stocks/bars?symbols=SPY&timeframe=1Day"
                                  "&start=2026-01-01T00:00:00Z&end=2026-02-01T00:00:00Z&adjustment=all&feed=sip")
        with self.assertRaises(TapeError) as caught:
            fold_tape(self.store, {**NEEDS, "symbols": ["QQQ"]}, "2025-08-01", "2025-09-01")
        self.assertIn("unfetched", str(caught.exception))
        # The seal's own door opens it.
        sealed = fold_tape(self.store, NEEDS, HOLDOUT[0], "2026-01-01", sealed=None)
        self.assertTrue(sealed["steps"])


class HoldoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.sqlite")
        self.seal = HoldoutSeal(self.ledger, budget=2)
        self.runs = []

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def run_it(self, window):
        self.runs.append(window)
        return {"base": {"ok": True, "return_pct": 3.12, "trades": 14, "max_drawdown": 0.02, "blocks": [{"log_growth": 0.1}]},
                "stressed": {"ok": True, "return_pct": 1.5, "trades": 14}}

    def test_one_evaluation_per_version_logged_coarse_and_rationed_per_lineage(self):
        first = self.seal.evaluate(agent="a1", lineage="L", code="x = 1", params={"k": 1}, run=self.run_it, passed=lambda r: True)
        self.assertEqual(first, {"evaluated": True, "passed": True, "return_pct": 3, "trades": "10-49"})
        self.assertNotIn("blocks", first)
        self.assertNotIn("max_drawdown", first)
        self.assertEqual(self.runs, [HOLDOUT])
        again = self.seal.evaluate(agent="a1", lineage="L", code="x = 1", params={"k": 1}, run=self.run_it, passed=lambda r: True)
        self.assertFalse(again["evaluated"])
        self.assertEqual(len(self.runs), 1)
        # Any agent of any lineage asking about the same version is refused too.
        self.assertFalse(self.seal.evaluate(agent="b", lineage="M", code="x = 1", params={"k": 1}, run=self.run_it, passed=bool)["evaluated"])
        self.seal.evaluate(agent="a1", lineage="L", code="x = 1", params={"k": 2}, run=self.run_it, passed=lambda r: False)
        spent = self.seal.evaluate(agent="a1", lineage="L", code="x = 2", params={"k": 2}, run=self.run_it, passed=lambda r: True)
        self.assertIn("spent its 2", spent["refused"])
        self.assertEqual(len(self.runs), 2)
        rows = list(self.ledger.iter(kinds="holdout.access"))
        self.assertEqual([r.payload["state"] for r in rows], ["opened", "evaluated", "opened", "evaluated"])
        self.assertFalse(rows[0].public)
        self.assertEqual(rows[1].payload["_detail"]["base"]["max_drawdown"], 0.02)  # the detail stays private in the ledger
        self.assertEqual(rows[1].payload["_detail"]["stressed"]["return_pct"], 1.5)
        self.assertNotIn("blocks", rows[1].payload["_detail"]["base"])

    def test_a_crashed_holdout_run_still_spends_the_access(self):
        def boom(window):
            raise RuntimeError("box died")
        out = self.seal.evaluate(agent="a", lineage="L", code="y", params={}, run=boom, passed=bool)
        self.assertFalse(out["evaluated"])
        self.assertEqual(self.seal.used("L"), 1)
        self.assertFalse(self.seal.evaluate(agent="a", lineage="L", code="y", params={}, run=self.run_it, passed=bool)["evaluated"])
        self.assertEqual(self.runs, [])
        self.assertNotEqual(version_of("y", {}), version_of("y", {"a": 1}))




# ------------------------------------------------------------------ the House

from unittest.mock import patch  # noqa: E402

from league.evaluator import Verdict  # noqa: E402
from league.tests.test_house import HouseCase  # noqa: E402

SPY_BUYER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-deep", "symbols": ["SPY"],
         "bars": {"timeframe": "1Hour", "limit": 5}, "wake_minutes": 60}
PARAMS = {"notional": 20.0}

def decide(ctx):
    held = [p for p in ctx["positions"] if p["symbol"] == "SPY"]
    if held:
        return {"intents": [{"symbol": "SPY", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "off"}]}
    return {"intents": [{"symbol": "SPY", "side": "buy", "notional_usd": ctx["params"]["notional"], "type": "market", "reason": "on"}]}
'''


class HouseDeepReplayTest(HouseCase):
    def setUp(self):
        super().setUp()
        self.house.holdout_window = ("2025-06-02", "2025-06-16")
        self.house.settings.deep_replay_days = 14
        store = HistoryStore.at_root(self.house.root)
        ing = _ingestor(store, FakeAlpaca(), workers=2)
        ing.run(ing.plan(["SPY"], ["1Day", "1Hour"], "2025-04-01", "2025-07-01"))
        ing.run(ing.probe_plan(["SPY"], "2025-05-15", "2025-06-16", grid="1Hour"))
        store.close()
        self.needs = {"venue": "alpaca", "horizon": "hour", "symbols": ["SPY"], "bars": {"timeframe": "1Hour", "limit": 5}}

    def test_a_covered_strategy_replays_on_the_development_window_with_quotes(self):
        key, tape = self.house.tape_for(self.needs)
        self.assertTrue(key.startswith("deep:alpaca:SPY:1Hour"))
        self.assertEqual(tape["source"]["window"], ["2025-05-19", "2025-06-02"])
        last = parse_time(tape["steps"][-1]["t"])
        self.assertLessEqual(last, parse_time("2025-06-02T00:00:00Z"))  # never into the holdout
        self.assertTrue(any(step.get("quotes") for step in tape["steps"]))
        self.assertGreater(tape["quote_source"]["quoted_touches"], 0)

    def test_replay_coverage_says_which_history_judges_the_strategy(self):
        agent = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
        covered = self.house.research_coverage(agent)
        self.assertEqual(covered["history"]["tape"], "development window before the sealed holdout")
        self.assertEqual(covered["history"]["window"], ["2025-05-19", "2025-06-02"])
        live = self.house.research_coverage(agent, {**self.needs, "symbols": ["QQQ"]})
        self.assertEqual(live["history"]["tape"], "live recent tape")

    def test_an_unfetched_symbol_falls_back_to_the_live_tape(self):
        key, tape = self.house.tape_for({**self.needs, "symbols": ["QQQ"]})
        self.assertFalse(key.startswith("deep:"))
        self.assertNotIn("source", tape)
        self.house.settings.deep_replay = False
        key, _ = self.house.tape_for(self.needs)
        self.assertFalse(key.startswith("deep:"))

    def test_the_holdout_runs_base_and_double_spread_once_per_version(self):
        agent = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
        with patch.object(self.house.evaluator, "replay_gate", return_value=(True, [])):
            first = self.house._holdout(agent, agent.code, agent.needs, agent.params)
            again = self.house._holdout(agent, agent.code, agent.needs, agent.params)
        self.assertEqual(first["evaluated"], True)
        self.assertTrue(first["passed"])
        self.assertEqual(set(first), {"evaluated", "passed", "return_pct", "trades"})
        self.assertFalse(again["evaluated"])
        rows = list(self.house.ledger.iter(kinds="holdout.access"))
        self.assertEqual([r.payload["state"] for r in rows], ["opened", "evaluated"])
        detail = rows[1].payload["_detail"]
        self.assertEqual(detail["stressed"]["execution"]["spread_stress"], 2.0)
        self.assertGreater(detail["base"]["execution"]["touch"].get("quoted", 0), 0)

    def _passing(self, agent_id, family, result, *, tape_id="", promote=True, lineage=None):
        return Verdict(agent_id, 0, "hold", "passed replay; no promotion was asked for or due", {"passed": True, "reasons": []})

    def test_a_deep_pass_is_promoted_only_when_the_holdout_agrees(self):
        for holdout, rung in (({"evaluated": True, "passed": False}, 0), ({"evaluated": True, "passed": True}, 1)):
            agent = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
            with patch.object(self.house.evaluator, "record_trial", side_effect=self._passing) as recorded, \
                    patch.object(type(self.house), "_holdout", return_value=holdout) as sealed:
                out = self.house._replay_own(agent)
            self.assertFalse(recorded.call_args.kwargs["promote"])  # the development pass alone promotes nothing
            sealed.assert_called_once()
            self.assertEqual(out["holdout"], holdout)
            self.assertEqual(self.house.evaluator.rung(agent.id), rung)

    def test_a_holdout_refusal_is_said_and_a_clone_of_a_paper_agent_gives_up_its_seat(self):
        """Sept 22, 2026: mcentee-32 and -33 passed replay, the lineage's holdout ration was spent by
        clones of their own code, their code was marked as tried, and nothing said so: they sat on
        rung 0 for good. The refusal is now a progress row, and a clone of a paper agent retires."""
        refused = {"evaluated": False, "refused": "the lineage has spent its 3 holdout evaluations"}
        alone = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
        with patch.object(self.house.evaluator, "record_trial", side_effect=self._passing), \
                patch.object(type(self.house), "_holdout", return_value=refused):
            self.house._replay_own(alone)
        rows = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=alone.id) if e.payload.get("stage") == "holdout"]
        self.assertEqual(len(rows), 1)
        self.assertIn("lineage has spent its 3 holdout evaluations", rows[0]["reason"])
        self.assertIn(alone.id, {a.id for a in self.house.registry.living()})  # nothing on paper runs its code
        self.house.evaluator.seat(alone.id, 1, "test")                        # now the same program trades on paper...
        clone = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a House mutation")
        with patch.object(self.house.evaluator, "record_trial", side_effect=self._passing), \
                patch.object(type(self.house), "_holdout", return_value=refused):
            self.house._replay_own(clone)
        died = self.house.ledger.last("agent.died", agent=clone.id)
        self.assertEqual(died.payload["cause"], "redundant")                  # ...so the clone gives up its seat

    def test_a_researchers_replay_is_development_history_fold_by_fold_and_never_the_holdout(self):
        agent = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
        out = self.house._candidate_replay(agent, SPY_BUYER.replace('"notional": 20.0', '"notional": 25.0'))
        self.assertTrue(out["counted_as_trial"], out)
        self.assertTrue(out["walk_forward"])
        self.assertTrue(all(fold["fold"][1] <= self.house.holdout_window[0] for fold in out["walk_forward"]))
        self.assertIn("holdout", out["note"])
        self.assertNotIn("holdout", {k for k in out if k != "note"})
        self.assertEqual(self.house.ledger.count(kinds="holdout.access"), 0)

    def test_a_live_tape_pass_is_promoted_as_before(self):
        self.house.settings.deep_replay = False
        agent = self.house.spawn("deep", "test-deep", SPY_BUYER, reason="a test agent")
        with patch.object(self.house.evaluator, "record_trial", side_effect=self._passing) as recorded, \
                patch.object(type(self.house), "_holdout") as sealed:
            self.house._replay_own(agent)
        self.assertTrue(recorded.call_args.kwargs["promote"])
        sealed.assert_not_called()




class DevDaysTest(unittest.TestCase):
    def test_a_development_tape_is_never_larger_than_the_largest_live_one(self):
        from league.deep_replay import dev_days
        five = {"horizon": "day", "symbols": ["SPY", "QQQ", "IWM", "TLT", "GLD"]}
        twelve = {"horizon": "day", "symbols": [f"S{i}" for i in range(12)], "observe": {"symbols": ["X1", "X2"]}}
        self.assertEqual(dev_days(five), 252)
        self.assertEqual(dev_days(twelve), 126)  # 14 symbols: cut to one fold, the live tape's own length
        self.assertEqual(dev_days({"horizon": "hour", "symbols": ["BTC/USD"]}), 63)
        self.assertEqual(dev_days({"horizon": "hour", "symbols": ["SPY"]}, 14), 14)




class CoverageGapTest(unittest.TestCase):
    def test_an_intraday_signal_needs_its_raw_series_and_the_daily_pairs_not_an_adjusted_one(self):
        from league.deep_replay import coverage_gaps
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            ing = _ingestor(store, FakeAlpaca(), workers=2)
            ing.run(ing.plan(["SPY"], ["5Min"], "2025-03-01", "2025-04-01", five_minute=("SPY",)))
            gaps = coverage_gaps(store, ["SPY"], "5Min", "2025-03-01", "2025-03-10", "2025-04-01")
            self.assertTrue(gaps and all("1Day" in g for g in gaps))  # the scaling pairs are missing, nothing else
            ing.run(ing.plan(["SPY"], ["1Day"], "2025-01-01", "2025-05-01"))
            self.assertEqual(coverage_gaps(store, ["SPY"], "5Min", "2025-03-01", "2025-03-10", "2025-04-01"), [])
            store.close()




class WalkForwardTest(unittest.TestCase):
    def test_blocks_are_cut_into_their_folds_oldest_first(self):
        from league.deep_replay import walk_forward
        tape = {"horizon": "day", "source": {"window": ["2025-03-07", "2025-11-14"]}}
        blocks = [{"key": "2025-03-10", "log_growth": 0.01, "active": True}, {"key": "2025-07-10", "log_growth": -0.02, "active": True},
                  {"key": "2025-07-11", "log_growth": 0.03, "active": False}, {"key": "2025-11-13", "log_growth": 0.01, "active": True}]
        out = walk_forward({"blocks": blocks}, tape)
        self.assertEqual([f["fold"] for f in out], [["2025-03-07", "2025-07-11"], ["2025-07-11", "2025-11-14"]])
        self.assertEqual([f["blocks"] for f in out], [2, 2])
        self.assertAlmostEqual(out[0]["log_growth"], -0.01)
        self.assertEqual(out[1]["active_blocks"], 1)
        self.assertEqual(walk_forward({"blocks": blocks}, {"horizon": "day"}), [])  # a live tape has no folds


if __name__ == "__main__":
    unittest.main()

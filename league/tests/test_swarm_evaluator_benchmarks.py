"""The evaluator benchmark suite: pinned cases, the static contract's answers, variant judging and the fast probes.

The full suite (eight worlds through every stage) runs from the CLI, not here: these tests check its parts on one
validation-only world so CI stays fast. Synthetic stores only.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.gym.experiment import check_experiment
from league.gym.safety import CodeRefused
from league.swarm import evaluator_benchmarks as EB

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

REFUSED = {"leak_array_base", "leak_private_attr", "leak_date_literal"}


class PinnedDefinition(unittest.TestCase):
    def test_the_pin_is_the_suites_hash(self):
        # A change to any case, template, world setting, variant or line of the suite's code moves the hash: bump
        # SUITE_ID and re-pin deliberately, never quietly.
        self.assertEqual(EB.PINNED_SUITE_SHA, EB.suite_fingerprint())

    def test_every_case_has_a_known_answer(self):
        ids = [c["id"] for c in EB.CASES]
        self.assertEqual(len(ids), len(set(ids)))
        kinds = {c["kind"] for c in EB.CASES}
        self.assertEqual(kinds, {"negative", "positive", "proof", "ablation"})
        for case in EB.CASES:
            if case.get("finding"):
                self.assertIn(case["finding"]["code_excerpt"], EB.render(case, _tiny_world()), case["id"])

    def test_worlds_are_deterministic_and_independent(self):
        self.assertEqual(EB.truth(3), EB.truth(3))
        self.assertNotEqual(EB.truth(3)["days"][10]["seed"], EB.truth(4)["days"][10]["seed"])
        windows = EB.sessions()
        self.assertGreaterEqual(min(len(windows["train"]) // 3, len(windows["validation"])), 60)


class StaticContract(unittest.TestCase):
    def test_leak_probes_are_refused_only_where_the_static_check_can_see_them(self):
        world = _tiny_world()
        for case in (c for c in EB.CASES if c["kind"] in ("negative", "positive")):
            code = EB.render(case, world)
            if case["id"] in REFUSED:
                with self.assertRaises(CodeRefused, msg=case["id"]):
                    check_experiment(code, {})
            else:
                check_experiment(code, {})

    def test_the_static_contract_sees_one_of_three_broken_switches(self):
        refused = {}
        for case in (c for c in EB.CASES if c["kind"] == "ablation"):
            try:
                check_experiment(EB.render(case), {"signal_on": 0})
                refused[case["id"]] = False
            except CodeRefused:
                refused[case["id"]] = True
        self.assertEqual({k for k, v in refused.items() if v}, {"ablation_shadow_config"})


class Variants(unittest.TestCase):
    def row(self, trades_per_year, validation_trades):
        years = {str(y): {"trades": trades_per_year, "days_traded": trades_per_year, "pnl": 10.0, "t_daily": 2.0}
                 for y in (2022, 2023, 2024)}
        checks = {"status_ok": True, "trades": validation_trades >= 50, "days": validation_trades >= 25, "mean_positive": True,
                  "t": True, "dsr": True, "quarters": True, "stress": True}
        return {"stages": {"static": True, "train_eligible": trades_per_year >= 40, "train_stress": True, "drift": True,
                           "validation": all(checks.values()), "review": True, "holdout": True},
                "train": {"status": "ok", "years": years, "quarters": "12/12", "trades": 3 * trades_per_year,
                          "days_traded": 3 * trades_per_year, "t_daily": 3.0, "pnl": 30.0},
                "validation": {"checks": checks, "numbers": {"trades": validation_trades, "days": validation_trades}}}

    def test_floors_are_the_only_difference_between_current_and_sparse_floors(self):
        sparse, dense = self.row(12, 12), self.row(60, 60)
        self.assertFalse(EB.variant_verdict(sparse, EB.VARIANTS["current"]))
        self.assertTrue(EB.variant_verdict(sparse, EB.VARIANTS["sparse_floors"]))
        self.assertTrue(EB.variant_verdict(dense, EB.VARIANTS["current"]))
        failing = self.row(12, 12)
        failing["validation"]["checks"]["t"] = False
        self.assertFalse(EB.variant_verdict(failing, EB.VARIANTS["no_floors"]))  # t >= 2 never loosens

    def test_the_current_variant_reproduces_the_pipelines_verdict(self):
        for row in (self.row(12, 12), self.row(45, 45), self.row(60, 60)):
            self.assertEqual(EB.variant_verdict(row, EB.VARIANTS["current"]), all(row["stages"].values()))

    def test_search_lineage_is_deterministic_and_uses_the_real_lines(self):
        first = EB.search_trial("signal_sparse", 0)
        self.assertEqual(first, EB.search_trial("signal_sparse", 0))
        self.assertEqual(first["current"]["candidates"], 0)  # 12 trades a year: never Train-eligible today
        self.assertEqual(set(first), set(EB.VARIANTS))


class Cli(unittest.TestCase):
    def test_benchmarks_dispatches_the_evaluator_suite(self):
        from league.swarm import benchmarks

        with mock.patch.object(EB, "main", return_value=7) as called:
            self.assertEqual(benchmarks.main(["--suite", "evaluator", "--json"]), 7)
        called.assert_called_once_with(["--suite", "evaluator", "--json"])


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class OneWorld(unittest.TestCase):
    """The validation window of one world: the planted signal is real, the invalid fills are not, STATE resets."""

    @classmethod
    def setUpClass(cls):
        from league.gym.store import Store

        cls.dir = Path(tempfile.mkdtemp(prefix="evaluator-suite-test-"))
        world = EB.truth(0)
        cls.world = {**world, **EB.write_world(cls.dir, world, windows=("validation",))}
        cls.store = Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        EB.clear_numpy_marks()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def load(self, case_id, params=None):
        from league.gym.runtime import load_program

        case = next(c for c in EB.CASES if c["id"] == case_id)
        return load_program(EB.render(case, self.world), name=case_id, params=params or {})

    def test_planted_moves_follow_the_tells_and_the_absent_channel_is_noise(self):
        rows = [(r, m) for r, m in zip(self.world["days"], self.world["moves"]) if m and r["window"] != "history"]
        dense = sum(m["dense"] * r["tells"][EB.CHANNELS["dense"]["k"]] for r, m in rows) / len(rows)
        absent = sum(m["absent"] * r["tells"][EB.CHANNELS["absent"]["k"]] for r, m in rows) / len(rows)
        self.assertGreater(dense, 0.4)
        self.assertLess(abs(absent), 0.3)

    def test_no_invalid_fill_is_ever_made(self):
        names = ("fill_close_above_width", "fill_open_below_zero", "fill_crossed_quotes", "fill_stale_quote")
        results = EB.run([self.load(n) for n in names], self.store, "validation")
        for name, result in zip(names, results):
            self.assertEqual(result["status"], "ok", name)
            self.assertGreater(result["summary"]["trades"], 40, name)  # the probes do trade: the market is there
            self.assertLess(result["summary"]["pnl"], 0.0, name)
            self.assertEqual(EB.impossible_fills(name, result), 0, name)
        for t in results[0]["trades"] + results[1]["trades"]:  # a 1-wide debit vertical trades inside [0, 1]
            self.assertGreater(t["entry"], 0.0)
            self.assertLessEqual(t["entry"], 1.0)
            self.assertLessEqual(t["exit"], 1.0)

    def test_historical_volume_without_receipts_is_hidden(self):
        [result] = EB.run([self.load("leak_volume_bars")], self.store, "validation")
        self.assertEqual({t.get("tag") for t in result["trades"]}, {"coin"})

    def test_state_resets_and_the_numpy_probe_measures_its_channel(self):
        import numpy as np
        from league.gym.runtime import load_program

        fresh = self.load("state_fresh_runs")
        first, second = EB.run([fresh], self.store, "validation"), EB.run([fresh], self.store, "validation")
        self.assertEqual(EB.trade_rows(first[0]), EB.trade_rows(second[0]))
        self.assertEqual(len(first[0]["trades"]), 5)
        try:
            probe = load_program(EB.STATE_PROGRAMS["state_numpy_runs"].lstrip("\n"), name="numpy-runs")
        except CodeRefused:
            return  # the static check closes the channel: the proof holds by refusal
        try:
            EB.clear_numpy_marks()
            [clean] = EB.run([probe], self.store, "validation")
            np.typecodes[EB.NUMPY_MARK_PREFIX + "run"] = "1"  # what an earlier run in this process leaves behind
            [marked] = EB.run([probe], self.store, "validation")
        finally:
            self.assertGreaterEqual(EB.clear_numpy_marks(), 1)
        self.assertGreater(len(clean["trades"]), 0)
        self.assertEqual(len(marked["trades"]), 0)

    def test_the_batch_mate_probe_compares_a_reader_alone_and_after_a_writer(self):
        out = EB.mates(self.store, "state_ctx_mate_writer", "state_ctx_mate_reader", "claim")
        if "refused" in out:
            return  # the static check closes the channel
        self.assertGreater(out["trades"][0], 50)
        self.assertEqual(out["held"], out["trades"][0] == out["trades"][1])

    def test_ablation_probe_tells_a_working_switch_from_an_ignored_one(self):
        on, off = self.load("ablation_ctx_params"), self.load("ablation_ctx_params", {"signal_on": 0})
        ignored_off = self.load("ablation_read_ignored", {"signal_on": 0})
        results = EB.run([on, off, ignored_off], self.store, "validation")
        self.assertGreater(len(results[0]["trades"]), 50)
        self.assertEqual(len(results[1]["trades"]), 0)
        self.assertEqual(len(results[2]["trades"]), len(results[0]["trades"]))

    def test_the_level_probe_world_scales_prices_and_nothing_else(self):
        from league.gym.store import Store

        scaled_dir = Path(tempfile.mkdtemp(prefix="evaluator-suite-scaled-"))
        try:
            EB.write_world(scaled_dir, EB.truth(0), level_scale=1.25, windows=("validation",))
            dense = self.load("planted_dense")
            [normal] = EB.run([dense], self.store, "validation")
            [scaled] = EB.run([dense], Store(scaled_dir), "validation")
        finally:
            shutil.rmtree(scaled_dir, ignore_errors=True)
        self.assertEqual([t["type"] for t in normal["trades"]], [t["type"] for t in scaled["trades"]])
        self.assertAlmostEqual(normal["summary"]["t_daily"], scaled["summary"]["t_daily"], delta=0.2)


def _tiny_world():
    world = EB.truth(0)
    return {**world, "moves": [{"absent": 1.0} if r["window"] != "history" else {} for r in world["days"]],
            "opens": [400.0 + i * 0.37 for i in range(len(world["days"]))]}


if __name__ == "__main__":
    unittest.main()

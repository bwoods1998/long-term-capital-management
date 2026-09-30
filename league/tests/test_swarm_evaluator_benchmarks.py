"""The evaluator benchmark suite: pinned cases, the static contract's answers, variant judging, the report's own
arithmetic (aggregate, headline, compare, receipt, exit codes) and the fast probes.

The full suite (eight worlds through every stage) runs from the CLI, not here: these tests check its parts on one
validation-only world and on fabricated rows so CI stays fast. Synthetic stores only.
"""

import json
import random
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

#: Probes the static check refuses today. The check may come to refuse more (release B's numpy fix refuses the memo
#: probe), never fewer: a test of containment, not equality.
REFUSED = {"leak_array_base", "leak_private_attr", "leak_date_literal"}


class PinnedDefinition(unittest.TestCase):
    def test_the_pin_is_the_suites_hash(self):
        # A change to any case, template, world setting, variant or line of the suite's code moves the hash: bump
        # SUITE_ID and re-pin deliberately, never quietly.
        self.assertEqual(EB.source_pin(), EB.suite_fingerprint())
        self.assertEqual(EB.PINNED_SUITE_SHA, EB.source_pin())

    def test_every_case_has_a_known_answer(self):
        ids = [c["id"] for c in EB.CASES]
        self.assertEqual(len(ids), len(set(ids)))
        kinds = {c["kind"] for c in EB.CASES}
        self.assertEqual(kinds, {"negative", "positive", "smoke", "proof", "ablation"})
        for case in EB.CASES:
            if case.get("finding"):
                self.assertIn(case["finding"]["code_excerpt"], EB.render(case, _tiny_world()), case["id"])

    def test_worlds_are_deterministic_and_independent(self):
        self.assertEqual(EB.truth(3), EB.truth(3))
        self.assertNotEqual(EB.truth(3)["days"][10]["seed"], EB.truth(4)["days"][10]["seed"])
        windows = EB.sessions()
        self.assertGreaterEqual(min(len(windows["train"]) // 3, len(windows["validation"])), 60)

    def test_cohorts_are_independent_and_development_keeps_its_streams(self):
        # Development's streams are the suite's first ones (EVALUATOR_1); confirmation's never repeat them.
        self.assertEqual(EB._seed("development", "world", 0), EB.digest([EB.SUITE_ID, "world", 0]))
        self.assertNotEqual(EB.truth(0)["days"][10]["seed"], EB.truth(0, "confirmation")["days"][10]["seed"])
        dev = EB.search_outcomes("noise_low_search", 0, 0, [2025])
        conf = EB.search_outcomes("noise_low_search", 0, 0, [2025], cohort="confirmation")
        self.assertEqual(len(dev["trades"]), len(conf["trades"]))
        self.assertNotEqual([t["pnl"] for t in dev["trades"]], [t["pnl"] for t in conf["trades"]])
        with self.assertRaises(ValueError):
            EB.truth(0, "holdout")

    @unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
    def test_the_bounds_and_prices_are_the_suites_own_and_agree_with_the_trees(self):
        import numpy as np
        from league import stats
        from league.gym import greeks

        for n in (1, 8, 40, 136, 512):
            for k in sorted({0, 1, n // 3, n - 1, n}):
                self.assertAlmostEqual(EB.exact_upper(k, n, 0.025), stats.exact_upper(k, n, 0.025), places=9)
        x = np.linspace(-8.0, 8.0, 2001)
        self.assertTrue(np.array_equal(EB.norm_cdf(x), greeks.norm_cdf(x)))


class StaticContract(unittest.TestCase):
    def test_the_static_check_refuses_what_it_can_see_and_never_a_control(self):
        world = _tiny_world()
        refused = set()
        for case in (c for c in EB.CASES if c["kind"] in EB.PIPELINE_KINDS):
            try:
                check_experiment(EB.render(case, world), {})
            except CodeRefused:
                refused.add(case["id"])
        self.assertLessEqual(REFUSED, refused)
        controls = {c["id"] for c in EB.CASES if c["family"] == "signal" or c.get("review_dependent")}
        self.assertFalse(refused & controls, "a signal control or a memorized table must reach the pipeline")

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

    def test_a_memorized_session_list_recognizes_its_window_and_trades_on_memory(self):
        # The review-dependent probe the level-invariance probe cannot see: it must really carry its memory, or its
        # promotion in the suite would say nothing about the review's load.
        [result] = EB.run([self.load("leak_memorized_sessions")], self.store, "validation")
        rate = EB.hit_rate(result, self.world)
        self.assertGreater(rate["trades"], 50)
        self.assertGreater(rate["rate"], 0.95)

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


class Report(unittest.TestCase):
    """The code that produces the headline a release is compared on, on fabricated rows (no engine, no store)."""

    def rows(self, reps=4):
        out = []
        for r in range(reps):
            cases = {}
            for c in EB.CASES:
                if c["kind"] not in EB.PIPELINE_KINDS:
                    continue
                if c["id"] in ("leak_memorized_levels", "planted_regime_years") or (c["id"] == "planted_dense" and r):
                    row = _passing_row()
                elif c["id"] == "fill_crossed_quotes":
                    row = _stopped_row("train_stress", impossible=1 if r == 0 else 0)
                else:
                    row = _stopped_row("static" if c["id"] in REFUSED else "train_stress")
                promoted = row["promoted"] and not (c["id"] == "leak_memorized_levels" and r >= 2)
                row = {**row, "promoted": promoted, "stopped_at": None if promoted else row["stopped_at"] or "holdout"}
                if c["id"] == "leak_memorized_levels":  # promoted in 2 of 4 worlds, flagged in all 4
                    row["probes"] = {**row["probes"], "level_invariance": {"flagged": True}}
                    row["stages"] = {**row["stages"], "holdout": promoted}
                cases[c["id"]] = row
            proofs = {name: {"held": name != "state_ctx_batchmates", "claim": name, "trades": [5, 5]}
                      for name in ("state_fresh_runs", "state_ctx_batchmates")}
            ablations = {"ablation_ctx_params": {"broken": False, "static_refused": False, "behavioral_effective": True,
                                                 "static_reason": None},
                         "ablation_read_ignored": {"broken": True, "static_refused": False, "behavioral_effective": False,
                                                   "static_reason": None}}
            out.append({"cases": cases, "proofs": proofs, "ablations": ablations})
        return out

    def search(self):
        def trial(noise_looks):
            return {name: {"promoted": False, "candidates": 3, "validations": 2,
                           "looks": noise_looks if name in ("no_floors", "sparse_floors") else 0} for name in EB.VARIANTS}
        signal = {name: {"promoted": name != "current", "candidates": 1, "validations": 1, "looks": 1} for name in EB.VARIANTS}
        return {"noise_sparse_search": [trial(1), trial(0)], "signal_sparse": [signal, signal]}

    def report(self):
        out = EB.aggregate(self.rows(), self.search())
        report = {"suite": EB.SUITE_ID, "suite_sha": "s", "cohort": "development", "pinned": True, "full_protocol": True,
                  "tree": {"fixture_sha": "f"}, "runtime": {"python": "3", "numpy": "2", "elapsed_seconds": 1.0}, **out}
        report["headline"] = EB.headline(report)
        return report

    def test_rates_count_case_worlds_and_whole_cases(self):
        rates = self.report()["rates"]
        negatives = [c for c in EB.CASES if c["kind"] == "negative"]
        self.assertEqual(rates["false_promotion"]["count"], 2)
        self.assertEqual(rates["false_promotion"]["of"], 4 * len(negatives))
        self.assertEqual(rates["false_promotion_mechanical_scope"]["count"], 0)
        self.assertEqual((rates["negative_cases_promoted"]["count"], rates["negative_cases_promoted"]["of"]),
                         (1, len(negatives)))
        positives = [c for c in EB.CASES if c["kind"] == "positive"]
        self.assertEqual(rates["missed_signal"]["count"], 4 * len(positives) - 3 - 4)
        self.assertEqual(rates["positive_cases_missed_in_any_world"]["count"], len(positives) - 1)
        low, high = rates["false_promotion"]["lower_95"], rates["false_promotion"]["upper_95"]
        self.assertLess(low, rates["false_promotion"]["rate"])
        self.assertGreater(high, rates["false_promotion"]["rate"])

    def test_the_level_probe_counts_detections_among_promoted_runs_only(self):
        detected = self.report()["level_invariance_probe"]["detected"]
        self.assertEqual((detected["count"], detected["of"]), (2, 2))  # flagged 4 times, promoted twice
        self.assertLessEqual(detected["rate"], 1.0)

    def test_smoke_cases_are_recorded_and_kept_out_of_the_rates(self):
        report = self.report()
        self.assertEqual(report["cases"]["leak_events_next"]["kind"], "smoke")
        self.assertIn("leak_events_next", report["headline"]["promoted_by_case"])
        negatives = [c for c in EB.CASES if c["kind"] == "negative"]
        self.assertEqual(report["rates"]["false_promotion"]["of"], 4 * len(negatives))

    def test_the_headline_is_a_per_case_vector(self):
        head = self.report()["headline"]
        self.assertEqual(head["promoted_by_case"]["leak_memorized_levels"], 2)
        self.assertEqual(head["missed_by_case"]["planted_dense"], 1)
        self.assertEqual(head["refused"], sorted(REFUSED))
        self.assertEqual(head["impossible_fills"], 1)
        self.assertEqual(head["proofs_failed"], ["state_ctx_batchmates"])
        self.assertEqual(head["runtime"], {"python": "3", "numpy": "2"})
        self.assertIn("aligned_floors", head["owner_rule"])

    def test_the_owner_rule_has_power_and_rejects_the_no_floors_reference(self):
        report = self.report()
        no_floors = report["variants"]["no_floors"]["owner_rule"]
        self.assertFalse(no_floors["met"])
        self.assertEqual(no_floors["noise_bands_with_more_looks"], ["noise_sparse_search"])
        self.assertTrue(report["verdict_sensitivity"]["no_floors_rejected"])
        self.assertTrue(report["verdict_sensitivity"]["noise_looks_see_no_floors"])
        self.assertTrue(report["variants"]["current"]["owner_rule"]["checks"]["noise_looks_not_higher_in_any_band"])
        self.assertFalse(report["variants"]["current"]["owner_rule"]["met"])  # it does not lower misses against itself

    def test_compare_lists_regressions_case_by_case(self):
        old = self.report()
        new = json.loads(json.dumps(old["headline"]))
        new["promoted_by_case"]["leak_memorized_levels"] = 0
        new["promoted_by_case"]["fill_crossed_quotes"] = 2
        new["refused"] = sorted(REFUSED - {"leak_private_attr"})
        new["proofs_held"]["state_fresh_runs"] = 3
        new["ablations"]["ablation_read_ignored"]["static_refused"] = 4
        out = EB.compare(old, new)
        self.assertTrue(out["comparable"])
        self.assertIn("fill_crossed_quotes promoted: 0 then 2", out["regressions"])
        self.assertIn("leak_private_attr is no longer refused by the static check", out["regressions"])
        self.assertIn("proof state_fresh_runs held: 4 then 3", out["regressions"])
        self.assertIn("leak_memorized_levels promoted: 2 then 0", out["improvements"])
        self.assertIn("ablation_read_ignored static refusals: 0 then 4", out["improvements"])
        new["tree"] = {"fixture_sha": "other"}
        self.assertFalse(EB.compare(old, new)["comparable"])

    def test_the_receipt_keeps_a_reproducible_rows_digest(self):
        report = {**self.report(), "replication_rows": [{"cases": {}, "seconds": 1.0}, {"cases": {}, "seconds": 2.0}]}
        receipt = EB.receipt(report)
        self.assertNotIn("replication_rows", receipt)
        self.assertEqual(receipt["replication_rows_sha256"], EB.digest([{"cases": {}}, {"cases": {}}]))
        self.assertEqual(EB._headline_of(receipt), report["headline"])

    @unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
    def test_a_refused_numpy_probe_leaves_the_proofs_whole(self):
        # The recommended release-B fix refuses numpy's mutable module attributes. Then both batch-mate probes are
        # refused, the proofs hold by refusal, and the report is still built (no KeyError at the end of a long run).
        from league.gym import runtime

        real = runtime.load_program

        def refusing(code, *args, **kwargs):
            if "np.typecodes" in code:
                raise CodeRefused("numpy module attributes are not allowed (simulated)")
            return real(code, *args, **kwargs)

        def fake_run(programs, store, window, *, stress=1.0):
            return [{"status": "ok", "trades": [{"day": "2025-01-02"}] * 5, "summary": {}} for _ in programs]

        with mock.patch.object(runtime, "load_program", refusing), mock.patch.object(EB, "run", fake_run), \
                mock.patch.object(EB, "split_proof", lambda root: {"held": True, "claim": "stub"}), \
                mock.patch.object(EB, "mates", lambda *a, **k: {"held": True, "claim": "stub"}):
            proofs = EB.proofs(store=None, root=Path("unused"))
        self.assertEqual(set(proofs), {c["id"] for c in EB.CASES if c["kind"] == "proof"})
        self.assertTrue(proofs["state_numpy_runs"]["held"] and proofs["state_numpy_batchmates"]["held"])
        rows = self.rows(2)
        for row in rows:
            row["proofs"] = proofs
        out = EB.aggregate(rows, self.search())
        self.assertEqual(out["proofs"]["state_numpy_batchmates"]["held"], 2)
        self.assertNotIn("state", out["facts_contradicted"])

    def test_the_level_flag_counts_a_run_that_stopped_trading(self):
        self.assertTrue(EB._level_flag(3.0, None))
        self.assertTrue(EB._level_flag(3.0, 1.0))
        self.assertFalse(EB._level_flag(3.0, 2.9))
        self.assertFalse(EB._level_flag(1.0, None))
        self.assertFalse(EB._level_flag(None, 0.0))


class Admission(unittest.TestCase):
    def frozen(self, **changes):
        tree = {"execution_sha256": "e", "evaluator_sha": "v", "fixture_sha": "f"}
        return {"cohort": "development", "pinned": True, "suite_sha": "s", "replications": 8, "search_replications": 128,
                "tree": tree, "headline": {"suite": EB.SUITE_ID}, **changes}

    def test_confirmation_needs_the_frozen_development_report_of_the_same_suite_and_tree(self):
        tree = {"execution_sha256": "e", "evaluator_sha": "v", "fixture_sha": "f"}
        self.assertEqual(EB.admit_confirmation(self.frozen(), "s", 8, 128, tree), EB.digest({"suite": EB.SUITE_ID}))
        for bad in (None, self.frozen(cohort="confirmation"), self.frozen(suite_sha="t"), self.frozen(replications=4),
                    self.frozen(tree={**tree, "evaluator_sha": "w"}), self.frozen(pinned=False)):
            with self.assertRaises(ValueError):
                EB.admit_confirmation(bad, "s", 8, 128, tree)


class Cli(unittest.TestCase):
    def test_benchmarks_dispatches_the_evaluator_suite(self):
        from league.swarm import benchmarks

        with mock.patch.object(EB, "main", return_value=7) as called:
            self.assertEqual(benchmarks.main(["--suite", "evaluator", "--json"]), 7)
        called.assert_called_once_with(["--suite", "evaluator", "--json"])

    def fake(self, pinned):
        report = Report().report()
        return {**report, "pinned": pinned, "pinned_sha": "p" * 64, "suite_sha": "s" * 64, "replication_rows": []}

    def test_exit_codes(self):
        def quiet():
            return mock.patch("builtins.print")

        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", return_value=self.fake(False)):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 3)
        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", return_value=self.fake(True)):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 0)
        with quiet(), mock.patch.object(EB, "scorable", return_value=["league.gym.experiment.check_experiment"]):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 5)
        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", side_effect=ValueError("confirmation is not admissible")), \
                tempfile.TemporaryDirectory() as temp:
            frozen = Path(temp) / "dev.json"
            frozen.write_text("{}")
            self.assertEqual(EB.main(["--suite", "evaluator", "--cohort", "confirmation", "--frozen", str(frozen)]), 2)
        with quiet(), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            EB.main(["--suite", "evaluator", "--cohort", "confirmation"])

    def test_compare_exits_4_on_a_regression(self):
        old = self.fake(True)
        worse = json.loads(json.dumps(old["headline"]))
        worse["promoted_by_case"]["fill_stale_quote"] = 1
        with tempfile.TemporaryDirectory() as temp, mock.patch("builtins.print"), \
                mock.patch.object(EB, "scorable", return_value=[]), mock.patch.object(EB, "suite", return_value=old):
            path = Path(temp) / "old.json"
            path.write_text(json.dumps({"headline": worse}))
            self.assertEqual(EB.main(["--suite", "evaluator", "--compare", str(path)]), 0)  # the new run improved on it
            path.write_text(json.dumps({"headline": {**worse, "promoted_by_case": {
                **worse["promoted_by_case"], "fill_stale_quote": 0, "leak_memorized_levels": 0}}}))
            self.assertEqual(EB.main(["--suite", "evaluator", "--compare", str(path)]), 4)

    def test_tree_mode_runs_this_suite_file_in_a_child_with_the_tree_first(self):
        from types import SimpleNamespace

        tree = Path(EB.__file__).resolve().parents[2]
        args = SimpleNamespace(json=True, output=Path("out.json"), receipt=None, compare=None, frozen=None, scratch=None,
                               replications=2, search_replications=None, allow_unpinned=False, cohort="development")
        with mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as called:
            self.assertEqual(EB.run_on_tree(tree, args), 0)
        command = called.call_args.args[0]
        self.assertEqual(command[3:5], [str(tree), str(Path(EB.__file__).resolve())])
        self.assertIn("--cohort", command)
        self.assertEqual(command[command.index("--output") + 1], str(Path("out.json").resolve()))
        self.assertEqual(command[command.index("--replications") + 1], "2")
        self.assertNotIn("PYTHONPATH", called.call_args.kwargs["env"])


def _passing_row():
    years = {str(y): {"trades": 60, "days_traded": 60, "pnl": 10.0, "t_daily": 2.5} for y in (2022, 2023, 2024)}
    checks = {"status_ok": True, "trades": True, "days": True, "mean_positive": True, "t": True, "dsr": True,
              "quarters": True, "stress": True}
    return {"stages": {"static": True, "train_eligible": True, "train_stress": True, "drift": True, "validation": True,
                       "review": True, "holdout": True},
            "promoted": True, "stopped_at": None, "probes": {"stress_contaminated": False, "level_invariance": {"flagged": False}},
            "train": {"status": "ok", "years": years, "quarters": "12/12", "trades": 180, "days_traded": 180, "t_daily": 3.0,
                      "pnl": 30.0},
            "validation": {"checks": checks, "numbers": {"trades": 60, "days": 60}},
            "validation_pooled": {"checks": checks, "numbers": {"trades": 120, "days": 120}}}


def _stopped_row(stage, impossible=0):
    if stage == "static":
        return {"stages": {"static": False}, "promoted": False, "stopped_at": "static", "refused": "refused (fabricated)"}
    row = _passing_row()
    row["stages"] = {**row["stages"], stage: False}
    probes = {**row["probes"], "impossible_fills": impossible}
    return {**row, "promoted": False, "stopped_at": stage, "probes": probes}


def _tiny_world():
    world = EB.truth(0)
    rng = random.Random(0)
    return {**world, "moves": [{"absent": 1.0} if r["window"] != "history" else {} for r in world["days"]],
            "opens": [400.0 + i * 0.37 for i in range(len(world["days"]))],
            "marks": ["".join(rng.choice("ud") for _ in EB.MARK_INDEXES) for _ in world["days"]]}


if __name__ == "__main__":
    unittest.main()

"""Paired experiment tests with authored DB receipts; no provider requests."""

from copy import deepcopy
from decimal import Decimal
import gc
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import tracemalloc
import unittest

from portfolio_runtime.evaluation import evaluate


def encoded(value):
    return json.dumps(value, sort_keys=True)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_000_000), b""):
            digest.update(chunk)
    return digest.hexdigest()


def body(
    window="flex",
    *,
    prior=None,
    prefix="shared",
    facts=123,
    model="moonshotai/Kimi-K2.6",
    max_output=8192,
):
    packet = {
        "evidence": {"revenue": facts},
        "question": "What changes the investment case?",
    }
    if prior is not None:
        packet["prior_work"] = prior
    return {
        "model": model,
        "max_output_tokens": max_output,
        "background": True,
        "metadata": {"completion_window": window},
        "prompt_cache_key": "key-" + prefix,
        "input": [
            {
                "role": "system",
                "content": "Experiment context: " + prefix + ".\nSame source context.",
            },
            {"role": "user", "content": encoded(packet)},
        ],
    }


class RuntimeEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.request_path = Path(self.temp.name) / "requests.sqlite"
        self.research_path = Path(self.temp.name) / "research.sqlite"
        with sqlite3.connect(self.request_path) as db:
            db.executescript("""CREATE TABLE requests(id TEXT,task_id TEXT,profile TEXT,body TEXT,reserved TEXT,cost TEXT,
                response TEXT,status TEXT,created REAL,updated REAL,cache TEXT);
                CREATE TABLE allocations(id TEXT,reserved TEXT,cost TEXT,receipt TEXT);""")
        with sqlite3.connect(self.research_path) as db:
            db.executescript("""CREATE TABLE tasks(id TEXT,wave INTEGER,kind TEXT,symbol TEXT,profile TEXT,cache TEXT,
                body TEXT,request_id TEXT,status TEXT,grade TEXT);
                CREATE TABLE events(at REAL,kind TEXT,payload TEXT);""")
        self.number = 0

    def tearDown(self):
        self.temp.cleanup()

    def add(
        self,
        kind,
        *,
        wave=1,
        ticker="AAPL",
        profile="kimi_flex",
        cache="ordinary",
        request_body=None,
        cost="0.01",
        created=1000,
        updated=1010,
        status="completed",
        passed=True,
        attached=True,
        supercached=0,
        written=0,
        cached=100,
        input_tokens=1000,
        output_tokens=100,
    ):
        self.number += 1
        task_id, request_id = "task-" + str(self.number), "request-" + str(self.number)
        value = request_body or body()
        grade = (
            None
            if passed is None
            else encoded(
                {"source_check_passed": passed, "claims_checked": 3, "errors": []}
            )
        )
        response = {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_tokens_details": {"cached_tokens": cached},
            },
            "metadata": {
                "supercached_input_tokens": str(supercached),
                "supercache_write_input_tokens": str(written),
            },
            "output": [{"text": "PRIVATE RAW MODEL THESIS"}],
        }
        with sqlite3.connect(self.research_path) as db:
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    wave,
                    kind,
                    ticker,
                    profile,
                    cache,
                    encoded(value),
                    request_id if attached else None,
                    "complete" if status == "completed" else "running",
                    grade,
                ),
            )
        if attached:
            with sqlite3.connect(self.request_path) as db:
                db.execute(
                    "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        request_id,
                        task_id,
                        profile,
                        encoded(value),
                        "1",
                        cost,
                        encoded(response),
                        status,
                        created,
                        updated,
                        cache,
                    ),
                )
        return task_id, request_id

    def result(self):
        return evaluate(self.request_path, self.research_path)

    def window_triplet(self, *, wave=1, ticker="AAPL"):
        for window, cost, duration, passed in (
            ("asap", "0.10", 10, True),
            ("balanced", "0.07", 20, True),
            ("flex", "0.04", 40, False),
        ):
            self.add(
                "window_pair",
                wave=wave,
                ticker=ticker,
                profile="kimi_" + window,
                request_body=body(window, prefix="window-control"),
                cost=cost,
                updated=1000 + duration,
                passed=passed,
            )

    def test_empty_snapshot_has_no_manufactured_pairs_or_savings(self):
        result = self.result()
        self.assertEqual(result["requests"]["requests"], 0)
        self.assertEqual(result["completion_windows"]["matched_triplets"], 0)
        self.assertIsNone(result["supercache"]["observed_control_minus_read_cost_usd"])
        self.assertIsNone(result["supercache"]["inferred_reads_to_amortize_writes"])
        self.assertEqual(result["concurrency"]["peak_admitted_request_overlap"], 0)

    def test_windows_match_exact_inputs_and_report_paired_cost_latency_source_checks(
        self,
    ):
        self.window_triplet()
        windows = self.result()["completion_windows"]
        self.assertEqual(windows["matched_triplets"], 1)
        comparison = next(
            row
            for row in windows["paired_comparisons"]
            if row["left"] == "asap" and row["right"] == "flex"
        )
        self.assertEqual(comparison["cost_pairs"], 1)
        self.assertEqual(comparison["mean_right_minus_left_cost_usd"], "-0.06")
        self.assertEqual(comparison["mean_right_minus_left_seconds"], "30")
        self.assertEqual(comparison["source_checks"]["left_only_passed"], 1)
        self.assertEqual(windows["arms"]["flex"]["source_checks_passed"], 0)
        self.assertEqual(
            windows["arms"]["flex"]["intent_to_terminal"]["median_seconds"], 40
        )

    def test_missing_window_cells_remain_explicit_without_discarding_valid_pair(self):
        for window in ("asap", "flex"):
            self.add(
                "window_pair",
                profile="kimi_" + window,
                request_body=body(window, prefix="window-control"),
            )
        windows = self.result()["completion_windows"]
        self.assertEqual(windows["incomplete_groups"], 1)
        self.assertEqual(windows["missing_cells"]["balanced"], 1)
        pair = next(
            row
            for row in windows["paired_comparisons"]
            if row["left"] == "asap" and row["right"] == "flex"
        )
        self.assertEqual(pair["matched_inputs"], 1)

    def test_model_facts_or_output_limit_changes_exclude_window_comparison(self):
        self.add("window_pair", profile="kimi_asap", request_body=body("asap"))
        self.add("window_pair", profile="kimi_balanced", request_body=body("balanced"))
        self.add(
            "window_pair", profile="kimi_flex", request_body=body("flex", facts=124)
        )
        windows = self.result()["completion_windows"]
        self.assertEqual(windows["matched_triplets"], 0)
        self.assertEqual(windows["nonidentical_input_groups"], 1)
        self.assertEqual(
            next(
                row for row in windows["paired_comparisons"] if row["right"] == "flex"
            )["matched_inputs"],
            0,
        )

    def test_duplicate_arms_cannot_be_cherry_picked(self):
        self.window_triplet()
        self.add(
            "window_pair",
            profile="kimi_flex",
            request_body=body("flex", prefix="window-control"),
            cost="0.0001",
        )
        windows = self.result()["completion_windows"]
        self.assertEqual(windows["duplicate_arm_groups"], 1)
        self.assertEqual(windows["matched_triplets"], 0)

    def test_memory_comparison_requires_same_facts_and_nonempty_persistent_history(
        self,
    ):
        self.add(
            "company",
            request_body=body(prior=[{"thesis": "Earlier private work"}]),
            passed=False,
            cost="0.03",
        )
        self.add("fresh_review", request_body=body(prior=[]), passed=True, cost="0.01")
        memory = self.result()["memory"]
        self.assertEqual(memory["matched_pairs"], 1)
        self.assertEqual(
            memory["paired_comparison"]["mean_right_minus_left_cost_usd"], "-0.02"
        )
        self.assertEqual(
            memory["paired_comparison"]["source_checks"]["right_only_passed"], 1
        )

    def test_empty_history_and_changed_facts_do_not_support_memory_value(self):
        self.add("company", wave=1, request_body=body(prior=[]))
        self.add("fresh_review", wave=1, request_body=body(prior=[]))
        self.add("company", wave=2, request_body=body(prior=[{"thesis": "prior"}]))
        self.add("fresh_review", wave=2, request_body=body(prior=[], facts=999))
        memory = self.result()["memory"]
        self.assertEqual(memory["matched_pairs"], 0)
        self.assertEqual(memory["invalid_memory_assignment_pairs"], 1)
        self.assertEqual(memory["nonidentical_input_pairs"], 1)

    def test_cache_cost_includes_write_and_reads_without_inventing_control(self):
        self.add("cache_write", cache="write", cost="2", written=800)
        self.add("company", cache="read", cost="0.01", cached=800, supercached=800)
        self.add("company", cache="read", cost="0.02", cached=800, supercached=800)
        cache = self.result()["supercache"]
        self.assertEqual(cache["write_plus_read_known_cost_usd"], "2.03")
        self.assertEqual(cache["amortized_cost_per_read_usd"], "1.015")
        self.assertEqual(cache["reads"]["tokens"]["supercached_tokens"], 1600)
        self.assertEqual(cache["matched_control_pairs"], 0)
        self.assertIsNone(cache["inferred_reads_to_amortize_writes"])
        self.assertIsNone(cache["observed_pair_advantage_after_all_writes_usd"])

    def test_matched_cache_control_reports_actual_difference_after_write_and_conditional_break_even(
        self,
    ):
        self.add("cache_write", cache="write", cost="0.20", written=800)
        self.add(
            "company",
            cache="read",
            request_body=body(prefix="shared", prior=[]),
            cost="0.01",
            cached=800,
            supercached=800,
        )
        self.add(
            "cache_control",
            request_body=body(prefix="ordinary-cache-control", prior=[]),
            cost="0.06",
        )
        cache = self.result()["supercache"]
        self.assertEqual(cache["matched_control_pairs"], 1)
        self.assertEqual(cache["observed_control_minus_read_cost_usd"], "0.05")
        self.assertEqual(cache["observed_pair_advantage_after_all_writes_usd"], "-0.15")
        self.assertEqual(cache["inferred_reads_to_amortize_writes"], 4)
        self.assertIn("Not a measured", cache["break_even_basis"])

    def test_automatic_supercache_hit_invalidates_ordinary_control(self):
        self.add(
            "company",
            cache="read",
            request_body=body(prefix="shared", prior=[]),
            supercached=80,
        )
        self.add(
            "cache_control",
            request_body=body(prefix="ordinary-cache-control", prior=[]),
            supercached=20,
        )
        cache = self.result()["supercache"]
        self.assertEqual(cache["matched_control_pairs"], 0)
        self.assertEqual(cache["contaminated_or_unverified_control_pairs"], 1)

    def test_unsettled_write_or_read_prevents_full_amortized_cost(self):
        self.add(
            "cache_write", cache="write", cost=None, status="in_progress", written=800
        )
        self.add("company", cache="read", cost="0.01", supercached=50)
        cache = self.result()["supercache"]
        self.assertFalse(cache["write_and_read_costs_complete"])
        self.assertIsNone(cache["amortized_cost_per_read_usd"])
        self.assertEqual(cache["writes"]["unsettled_requests"], 1)

    def test_unsettled_and_terminal_failure_are_not_counted_as_successful_work(self):
        self.add("company", cost=None, status="failed", passed=False)
        self.add("company", cost=None, status="in_progress", passed=None)
        result = self.result()["requests"]
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["terminal_failures"], 1)
        self.assertEqual(result["unsettled_requests"], 2)
        self.assertEqual(result["source_checks_evaluated"], 1)

    def test_concurrency_distinguishes_planned_limit_from_observed_overlap(self):
        with sqlite3.connect(self.research_path) as db:
            db.execute(
                "INSERT INTO events VALUES(?,?,?)",
                (999, "wave_planned", encoded({"wave": 1, "concurrency": 32})),
            )
        self.add("company", created=1000, updated=1010)
        self.add("company", created=1005, updated=1015)
        self.add("company", created=1015, updated=1020)
        concurrency = self.result()["concurrency"]
        self.assertEqual(concurrency["planned_levels"], [32])
        self.assertEqual(concurrency["peak_admitted_request_overlap"], 2)
        self.assertEqual(concurrency["cohorts"][0]["planned_concurrency"], 32)
        self.assertIn("not simultaneous", concurrency["measurement"])

    def test_request_body_binding_mismatch_cannot_inherit_source_grade(self):
        task, request = self.add("company")
        with sqlite3.connect(self.request_path) as db:
            db.execute(
                "UPDATE requests SET body=? WHERE id=?",
                (encoded(body(facts=999)), request),
            )
        result = self.result()
        self.assertEqual(result["mismatched_request_bindings"], 1)
        self.assertEqual(result["requests"]["source_checks_evaluated"], 0)

    def test_projection_leaks_neither_model_text_nor_identifiers_and_is_readonly(self):
        self.add("company", request_body=body(prior=[{"secret": "PRIVATE HISTORY"}]))
        before = (self.request_path.read_bytes(), self.research_path.read_bytes())
        output = encoded(self.result())
        for phrase in ("PRIVATE", "request-1", "task-1", "Earlier"):
            self.assertNotIn(phrase, output)
        self.assertEqual(
            before, (self.request_path.read_bytes(), self.research_path.read_bytes())
        )

    def test_delegated_cost_is_separate_from_unpaired_coordinator_requests(self):
        with sqlite3.connect(self.request_path) as db:
            db.executemany(
                "INSERT INTO allocations VALUES(?,?,?,?)",
                [("branch-1", "1", "0.3", "{}"), ("branch-2", "2", None, None)],
            )
        result = self.result()
        self.assertEqual(result["requests"]["requests"], 0)
        self.assertEqual(
            result["delegated_allowances"],
            {"count": 2, "unsettled": 1, "known_cost_usd": "0.3"},
        )

    def test_small_scientific_decimal_receipts_are_counted_exactly(self):
        self.add("company", cost="3E-8")
        self.assertEqual(self.result()["requests"]["known_cost_usd"], "0.00000003")

    def test_absent_database_is_not_created_by_evaluation(self):
        missing = self.request_path.parent / "missing.sqlite"
        with self.assertRaises(sqlite3.OperationalError):
            evaluate(missing, self.research_path)
        self.assertFalse(missing.exists())

    def test_long_prefix_snapshots_use_bounded_memory_and_preserve_request_bytes(self):
        prefix = "Same frozen evidence. " * 15000
        for wave in range(30):
            for window in ("asap", "balanced", "flex"):
                value = body(window, prior=[])
                value["input"][0]["content"] += prefix
                self.add(
                    "window_pair",
                    wave=wave,
                    profile="kimi_" + window,
                    request_body=value,
                )
        self.assertGreater(
            self.request_path.stat().st_size + self.research_path.stat().st_size,
            50_000_000,
        )
        before = tuple(
            file_hash(path) for path in (self.request_path, self.research_path)
        )
        gc.collect()
        tracemalloc.start()
        try:
            result = self.result()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result["completion_windows"]["matched_triplets"], 30)
        # Previous fetchall + decoded copies retained more than 100 MB here.
        self.assertLess(peak, 12_000_000)
        after = tuple(
            file_hash(path) for path in (self.request_path, self.research_path)
        )
        self.assertEqual(before, after)

    def test_large_prefix_hashes_retain_memory_cache_and_binding_differences(self):
        def long_value(**kwargs):
            value = body(**kwargs)
            value["input"][0]["content"] += "Frozen context. " * 20000
            return value

        self.add("company", wave=1, request_body=long_value(prior=[{"thesis": "old"}]))
        self.add("fresh_review", wave=1, request_body=long_value(prior=[]))
        self.add(
            "company",
            wave=2,
            cache="read",
            request_body=long_value(prefix="shared", prior=[]),
            cached=800,
            supercached=800,
        )
        self.add(
            "cache_control",
            wave=2,
            request_body=long_value(prefix="ordinary-cache-control", prior=[]),
        )
        changed = long_value(prefix="ordinary-cache-control", prior=[])
        changed["input"][0]["content"] += "Changed last byte"
        self.add(
            "company",
            wave=3,
            cache="read",
            request_body=long_value(prefix="shared", prior=[]),
            cached=800,
            supercached=800,
        )
        self.add("cache_control", wave=3, request_body=changed)
        task, request = self.add("company", wave=4, request_body=long_value(prior=[]))
        with sqlite3.connect(self.request_path) as db:
            db.execute(
                "UPDATE requests SET body=? WHERE id=?", (encoded(changed), request)
            )
        result = self.result()
        self.assertEqual(result["memory"]["matched_pairs"], 1)
        self.assertEqual(result["supercache"]["matched_control_pairs"], 1)
        self.assertEqual(result["supercache"]["nonidentical_control_pairs"], 1)
        self.assertEqual(result["mismatched_request_bindings"], 1)
        self.assertEqual(result["requests"]["source_checks_evaluated"], 6)


if __name__ == "__main__":
    unittest.main()

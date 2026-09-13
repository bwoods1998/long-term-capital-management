"""Offline policy trials through real task/receipt journals and fixed grading."""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from portfolio_runtime.improvement import (
    PolicyLab,
    holdout,
    required_claims,
    grade_trial,
)
from portfolio_runtime.provider import ClosingConnection, canonical
from portfolio_runtime.research import Research


def evidence(count=80):
    companies = []
    for n in range(count):
        symbol = f"C{n:03}"
        facts = {}
        for metric, tag, value in (
            ("operating_cash", "OperatingCashFlow", 100 + n),
            ("capital_spending", "CapitalSpending", 25 + n),
            ("revenue", "Revenue", 200 + n),
        ):
            facts[metric] = [
                {
                    "tag": tag,
                    "unit": "USD",
                    "observations": [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "filed": "2026-02-01",
                            "val": value,
                        }
                    ],
                }
            ]
        companies.append(
            {
                "symbol": symbol,
                "facts": facts,
                "source": "https://data.sec.gov/example.json",
                "sha256": "a" * 64,
            }
        )
    return {
        "companies": companies,
        "overview": [],
        "captured_at": "2026-09-14T12:00:00Z",
    }


def answer(company, *, good=True):
    result = {
        "thesis": "Current facts require further investigation.",
        "claims": required_claims(company),
        "questions": [],
        "targets": [],
        "confidence": "high",
        "abstain_reason": None,
    }
    if not good:
        result["claims"][0]["value"] = "99999999"
    return result


class Receipts:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE requests(id TEXT PRIMARY KEY,task_id TEXT UNIQUE,profile TEXT,body TEXT,cache TEXT,status TEXT,cost TEXT,response TEXT,response_id TEXT,created REAL,updated REAL)"
            )

    def connect(self):
        db = sqlite3.connect(self.path, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def complete(
        self,
        research,
        *,
        good=lambda task: task["id"].endswith("challenger"),
        unknown=None,
        cost=None,
    ):
        with research.connect() as db:
            tasks = list(db.execute("SELECT * FROM tasks WHERE kind='policy_trial'"))
        with self.connect() as db:
            for task in tasks:
                packet = json.loads(json.loads(task["body"])["input"][-1]["content"])
                result = answer(packet["evidence"], good=good(task))
                response = {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": canonical(result)}
                            ],
                        }
                    ]
                }
                db.execute(
                    "INSERT OR IGNORE INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "request-" + task["id"],
                        task["id"],
                        task["profile"],
                        task["body"],
                        task["cache"],
                        "completed",
                        None
                        if unknown and unknown(task)
                        else cost(task)
                        if cost
                        else "0.01",
                        canonical(response),
                        "response-" + task["id"],
                        100,
                        110,
                    ),
                )


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lab = PolicyLab(self.root / "improvement.sqlite")
        self.bank = evidence()

    def tearDown(self):
        self.temp.cleanup()

    def research(self, name):
        research = Research(self.root / (name + ".sqlite"), self.bank)
        research.latest = lambda symbol, limit: [
            {
                "result": answer(research.companies[symbol]),
                "grade": {"source_check_passed": True},
                "source_cutoff": "2026-09-13",
            }
        ]
        return research

    def campaign(self, start, *, days=2, good=None, unknown=None, cost=None):
        latest = None
        for day in range(days):
            cutoff = (
                date.fromisoformat(start) + timedelta(days=day)
            ).isoformat() + "T12:00:00Z"
            for epoch in range(4):
                name = f"epoch-{start}-{day}-{epoch}-v{self.lab.policy()['version']}"
                research = self.research(name)
                self.lab.plan_epoch(research, epoch_id=name, cutoff=cutoff)
                client = Receipts(self.root / (name + "-requests.sqlite"))
                options = {"unknown": unknown, "cost": cost}
                if good:
                    options["good"] = good
                client.complete(research, **options)
                self.lab.reconcile(research, client)
                latest = research, client
        return latest

    def test_plan_is_paired_fixed_dated_and_idempotent_without_provider_calls(self):
        research = self.research("first")
        ids = self.lab.plan_epoch(
            research, epoch_id="epoch-1", cutoff="2026-09-14T12:00:00Z"
        )
        self.assertEqual(len(ids), 4)
        with research.connect() as db:
            tasks = list(db.execute("SELECT * FROM tasks ORDER BY id"))
        self.assertEqual(len(tasks), 8)
        for i in range(0, 8, 2):
            a, b = tasks[i : i + 2]
            left, right = json.loads(a["body"]), json.loads(b["body"])
            self.assertEqual(left["model"], right["model"])
            self.assertEqual(left["max_output_tokens"], right["max_output_tokens"])
            self.assertEqual(left["input"][0], right["input"][0])
            lp = json.loads(left["input"][-1]["content"])
            rp = json.loads(right["input"][-1]["content"])
            self.assertNotEqual(bool(lp.pop("prior_work")), bool(rp.pop("prior_work")))
            self.assertEqual(lp, rp)
            self.assertEqual(a["kind"], "policy_trial")
        research.latest = lambda *args: [{"changed": "must not mutate accepted plan"}]
        self.assertEqual(
            self.lab.plan_epoch(
                research, epoch_id="epoch-1", cutoff="2026-09-14T12:00:00Z"
            ),
            ids,
        )
        with self.assertRaises(ValueError):
            self.lab.plan_epoch(
                research, epoch_id="epoch-1", cutoff="2026-09-15T12:00:00Z"
            )

    def test_single_pair_budget_does_not_starve_selection_and_cannot_backdate_sources(
        self,
    ):
        research = self.research("single")
        with self.assertRaises(ValueError):
            self.lab.plan_epoch(
                research, epoch_id="backdated", cutoff="2026-09-13", max_pairs=1
            )
        ids = self.lab.plan_epoch(
            research, epoch_id="single", cutoff="2026-09-14", max_pairs=1
        )
        self.assertEqual(len(ids), 1)
        with self.lab.connect() as db:
            self.assertEqual(
                db.execute("SELECT split FROM trials WHERE id=?", (ids[0],)).fetchone()[
                    0
                ],
                "selection",
            )

    def test_absent_memory_or_three_metrics_is_not_an_experiment(self):
        research = Research(self.root / "empty.sqlite", self.bank)
        self.assertEqual(
            self.lab.plan_epoch(research, epoch_id="empty", cutoff="2026-09-14"), []
        )
        self.assertEqual(self.lab.evaluate()["reason"], "insufficient_evidence")
        self.assertEqual(self.lab.policy()["name"], "memory_3")

    def test_predeclared_metric_period_checks_cannot_be_replaced_by_confidence_or_easy_claims(
        self,
    ):
        company = deepcopy(self.bank["companies"][0])
        required = required_claims(company)
        good = answer(company)
        self.assertTrue(grade_trial(good, company, required)["passed"])
        bad = answer(company, good=False)
        self.assertFalse(grade_trial(bad, company, required)["passed"])
        bad = answer(company)
        bad["claims"][0]["start"] = None
        self.assertFalse(grade_trial(bad, company, required)["passed"])
        bad = answer(company)
        bad["claims"] = [bad["claims"][1]] * 3
        self.assertFalse(grade_trial(bad, company, required)["passed"])
        bad = answer(company)
        bad["targets"] = [{"symbol": company["symbol"], "weight": "0.20"}]
        self.assertFalse(grade_trial(bad, company, required)["passed"])
        self.assertFalse(
            grade_trial({"confidence": "high", "score": 100}, company, required)[
                "passed"
            ]
        )

    def test_post_cutoff_facts_are_removed_from_both_arms(self):
        for company in self.bank["companies"]:
            company["facts"]["revenue"][0]["observations"].append(
                {
                    "start": "2026-01-01",
                    "end": "2026-09-30",
                    "filed": "2026-10-20",
                    "val": 999,
                }
            )
        research = self.research("dated")
        self.lab.plan_epoch(research, epoch_id="dated", cutoff="2026-09-14")
        with research.connect() as db:
            for row in db.execute("SELECT body FROM tasks"):
                packet = json.loads(json.loads(row[0])["input"][-1]["content"])
                self.assertNotIn("2026-10-20", canonical(packet["evidence"]))

    def test_twenty_distinct_paired_companies_two_dates_promote_and_reopen_durably(
        self,
    ):
        self.campaign("2026-09-14")
        decision = self.lab.evaluate()
        self.assertEqual(decision["action"], "promote")
        self.assertEqual(decision["samples"], 20)
        self.assertEqual(decision["companies"], 20)
        self.assertEqual(len(decision["dates"]), 2)
        self.assertEqual(
            decision["policy"], {"version": 1, "name": "fresh", "memory_limit": 0}
        )
        reopened = PolicyLab(self.lab.path)
        self.assertEqual(reopened.policy(), decision["policy"])
        self.assertEqual(reopened.evaluate()["reason"], "insufficient_evidence")
        with reopened.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE policies SET name='unreviewed' WHERE version=1")

    def test_single_date_ties_or_inconsistent_dates_never_promote(self):
        self.campaign("2026-09-14", days=1)
        self.assertEqual(self.lab.evaluate()["action"], "keep")
        self.campaign("2026-09-15", days=1, good=lambda task: True)
        result = self.lab.evaluate()
        self.assertEqual(result["action"], "keep")
        self.assertEqual(result["reason"], "no_consistent_improvement")
        self.assertEqual(self.lab.evaluate()["samples"], 0)

    def test_holdout_success_cannot_promote_a_losing_selection_policy(self):
        def outcome(task):
            challenger = task["id"].endswith("challenger")
            return challenger if holdout(task["symbol"]) else not challenger

        self.campaign("2026-09-14", good=outcome)
        result = self.lab.evaluate()
        self.assertEqual(result["action"], "keep")
        self.assertEqual(result["wins"], 0)
        self.assertGreater(self.lab.summary()["audit_observations"], 0)

    def test_pending_earlier_pair_cannot_be_skipped_for_later_winners(self):
        with_memory = self.research("pending-first")
        self.lab.plan_epoch(with_memory, epoch_id="pending-first", cutoff="2026-09-14")
        receipts = Receipts(self.root / "pending-requests.sqlite")
        receipts.complete(with_memory, unknown=lambda task: True)
        self.lab.reconcile(with_memory, receipts)
        self.campaign("2026-09-15", days=3)
        result = self.lab.evaluate()
        self.assertEqual(result["action"], "keep")
        self.assertEqual(result["reason"], "insufficient_evidence")
        self.assertLess(result["samples"], 20)

    def test_bound_receipts_are_regraded_and_cannot_change_after_settlement(self):
        research = self.research("receipts")
        self.lab.plan_epoch(research, epoch_id="receipts", cutoff="2026-09-14")
        receipts = Receipts(self.root / "receipts.sqlite")
        receipts.complete(research)
        self.assertEqual(
            self.lab.reconcile(research, receipts)["observations_recorded"], 8
        )
        self.assertEqual(
            self.lab.reconcile(research, receipts)["observations_recorded"], 0
        )
        with receipts.connect() as db:
            db.execute(
                "UPDATE requests SET cost='0.02' WHERE task_id LIKE '%challenger'"
            )
        with self.assertRaises(ValueError):
            self.lab.reconcile(research, receipts)

    def test_source_reliability_does_not_waive_cost_bound(self):
        self.campaign(
            "2026-09-14",
            cost=lambda task: "0.10" if task["id"].endswith("challenger") else "0.01",
        )
        result = self.lab.evaluate()
        self.assertEqual(result["action"], "keep")
        self.assertEqual(result["wins"], 20)
        self.assertEqual(self.lab.policy()["name"], "memory_3")

    def test_different_provider_inputs_cannot_enter_trial_results(self):
        research = self.research("wrong-receipt")
        self.lab.plan_epoch(research, epoch_id="wrong-receipt", cutoff="2026-09-14")
        receipts = Receipts(self.root / "wrong-receipts.sqlite")
        receipts.complete(research)
        with receipts.connect() as db:
            db.execute("UPDATE requests SET body='{}' WHERE task_id LIKE '%challenger'")
        with self.assertRaises(ValueError):
            self.lab.reconcile(research, receipts)

    def test_failed_look_is_consumed_and_later_test_uses_stricter_threshold(self):
        self.campaign("2026-09-14", good=lambda task: True)
        first = self.lab.evaluate()
        self.assertEqual(first["action"], "keep")
        self.assertEqual(first["look"], 1)
        self.campaign("2026-09-16")
        second = self.lab.evaluate()
        self.assertEqual(second["action"], "promote")
        self.assertEqual(second["look"], 2)
        self.assertLess(
            float(second["alpha_threshold"]), float(first["alpha_threshold"])
        )
        self.assertTrue(set(first["trial_ids"]).isdisjoint(second["trial_ids"]))

    def test_forward_regression_rolls_back_once_without_changing_trading_authority(
        self,
    ):
        self.campaign("2026-09-14")
        self.assertEqual(self.lab.evaluate()["action"], "promote")
        self.campaign("2026-09-16")
        result = self.lab.evaluate()
        self.assertEqual(result["action"], "rollback")
        self.assertEqual(
            result["policy"], {"version": 2, "name": "memory_3", "memory_limit": 3}
        )
        self.assertEqual(self.lab.evaluate()["reason"], "rollback_complete")
        research = self.research("after-rollback")
        self.assertEqual(
            self.lab.plan_epoch(
                research, epoch_id="after-rollback", cutoff="2026-09-18"
            ),
            [],
        )
        self.assertEqual(set(self.lab.policy()), {"version", "name", "memory_limit"})
        self.assertFalse(self.lab.summary()["investment_skill_assessed"])

    def test_two_non_improving_looks_stop_spending_on_the_fixed_comparison(self):
        for start in ("2026-09-14", "2026-09-16"):
            self.campaign(start, good=lambda task: True)
            self.assertEqual(self.lab.evaluate()["action"], "keep")
        summary = self.lab.summary()
        self.assertEqual(summary["experiment_status"], "comparison_exhausted")
        research = self.research("stopped")
        self.assertEqual(
            self.lab.plan_epoch(research, epoch_id="stopped", cutoff="2026-09-18"), []
        )
        self.assertEqual(self.lab.evaluate()["reason"], "comparison_exhausted")
        self.assertEqual(self.lab.policy()["version"], 0)

    def test_unresolved_cohort_blocks_more_comparisons_and_unknown_cost_is_not_zero(
        self,
    ):
        self.campaign(
            "2026-09-14", unknown=lambda task: task["id"].endswith("challenger")
        )
        before = self.lab.summary()
        self.assertEqual(before["trials"]["selection"], 20)
        self.assertEqual(before["experiment_status"], "awaiting_settlement")
        self.assertGreater(before["unsettled_or_unobserved_arms"], 0)
        self.assertIsNone(before["latest_selection_value"])
        research = self.research("blocked")
        self.assertEqual(
            self.lab.plan_epoch(research, epoch_id="blocked", cutoff="2026-09-16"), []
        )
        self.assertEqual(before["trials"], self.lab.summary()["trials"])

    def test_value_receipt_measures_net_source_gains_against_both_arm_costs(self):
        self.campaign(
            "2026-09-14",
            cost=lambda task: "0.015" if task["id"].endswith("challenger") else "0.01",
        )
        receipt = self.lab.evaluate()
        value = receipt["value"]
        self.assertEqual(value["net_additional_source_passes"], 20)
        self.assertEqual(value["comparison_cost_usd"], "0.500")
        self.assertEqual(value["policy_cost_delta_usd"], "0.100")
        self.assertEqual(
            value["net_additional_source_passes_per_comparison_usd"], "40.000000"
        )
        self.assertFalse(value["investment_value_assessed"])
        self.assertEqual(self.lab.summary()["latest_selection_value"], value)

    def test_ties_and_zero_cost_never_manufacture_marginal_value(self):
        self.campaign("2026-09-14", good=lambda task: True, cost=lambda task: "0")
        value = self.lab.evaluate()["value"]
        self.assertEqual(value["net_additional_source_passes"], 0)
        self.assertIsNone(value["net_additional_source_passes_per_comparison_usd"])
        self.assertIsNone(value["challenger_passes_per_usd"])


if __name__ == "__main__":
    unittest.main()

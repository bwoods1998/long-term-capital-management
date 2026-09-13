"""Forward feedback from real paper ledger fixtures; no provider or paid calls."""

from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from portfolio_runtime import PortfolioLedger, UniverseSnapshot, DailyBar
from portfolio_runtime.contracts import BenchmarkPoint, YAHOO_SP500TR
from portfolio_runtime.market import next_session, session_for_day
from portfolio_runtime.outcomes import OutcomeJournal
from test_runtime_market import (
    FixtureMarket,
    fixture,
    SUNDAY,
    MONDAY_CAPTURE,
    MONDAY_CLOSE_CAPTURE,
    MONDAY_OPEN,
)
from test_paper_ledger import quote


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = PortfolioLedger(self.root / "paper.sqlite", created_at=SUNDAY)
        self.ledger.register_universe(
            UniverseSnapshot(
                "universe",
                SUNDAY,
                SUNDAY,
                ("AAPL",),
                "https://example.com/membership",
                "2026-09-20T00:00:00Z",
            )
        )
        self.journal = OutcomeJournal(self.root / "outcomes.sqlite")
        session = next_session(SUNDAY)
        self.ledger.propose(
            "decision-one",
            decided_at=SUNDAY,
            targets={"AAPL": "0.1"},
            universe_id="universe",
            evidence_refs=["filing-one"],
            rationale="Dated original hypothesis.",
            expected_open_at=session.opens_at,
            calendar_source=session.source,
        )

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def fill(self):
        market = FixtureMarket(
            self.root / "market", now=MONDAY_CAPTURE, fixtures={"AAPL": fixture()}
        )
        market.fill_pending(self.ledger, now=MONDAY_CAPTURE)

    def close(self):
        market = FixtureMarket(
            self.root / "market",
            now=MONDAY_CLOSE_CAPTURE,
            fixtures={"AAPL": fixture(closed=True)},
        )
        market.mark_close(self.ledger, now=MONDAY_CLOSE_CAPTURE)

    def benchmark(self, at="2026-09-14T20:02:00Z"):
        for boundary, value in (
            (MONDAY_OPEN, "5000"),
            ("2026-09-14T20:00:00Z", "5050"),
        ):
            self.ledger.record_benchmark(
                BenchmarkPoint(
                    as_of=boundary,
                    value=value,
                    source=YAHOO_SP500TR,
                    captured_at=at,
                    source_sha256="a" * 64,
                ),
                recorded_at=at,
            )

    def test_pending_and_open_only_have_no_outcome_or_future_feedback(self):
        result = self.journal.observe(self.ledger, observed_at=SUNDAY)
        self.assertEqual(result["decision_cohorts"], 1)
        self.assertEqual(result["outcome_receipts"], 0)
        self.fill()
        self.assertEqual(
            self.journal.observe(self.ledger, observed_at=MONDAY_CAPTURE)[
                "outcome_receipts"
            ],
            0,
        )
        self.assertEqual(self.journal.context(cutoff=MONDAY_CAPTURE), [])
        self.assertFalse(result["expansion_eligible"])

    def test_sourced_close_matches_actual_net_ledger_returns_and_is_idempotent(self):
        self.fill()
        self.close()
        self.benchmark()
        at = "2026-09-14T20:02:00Z"
        self.assertEqual(
            self.journal.observe(self.ledger, observed_at=at)["receipts_added"], 1
        )
        self.assertEqual(
            self.journal.observe(self.ledger, observed_at=at)["receipts_added"], 0
        )
        outcome = self.journal.context(cutoff=at)[0]
        performance = self.ledger.public_state()["performance"]
        self.assertEqual(
            Decimal(outcome["portfolio_return_pct"]),
            Decimal(performance["time_weighted_return_pct"]),
        )
        self.assertEqual(
            Decimal(outcome["net_excess_percentage_points"]),
            Decimal(performance["benchmark"]["excess_return_percentage_points"]),
        )
        self.assertEqual(outcome["prior_rationale"], "Dated original hypothesis.")
        self.assertEqual(outcome["recorded_closes"], 1)
        self.assertLess(
            Decimal(outcome["portfolio_return_pct"]), Decimal("0.5")
        )  # Slippage retained.

    def test_late_benchmark_appends_receipt_without_rewriting_earlier_knowledge(self):
        self.fill()
        self.close()
        self.journal.observe(self.ledger, observed_at=MONDAY_CLOSE_CAPTURE)
        first = self.journal.context(cutoff=MONDAY_CLOSE_CAPTURE)
        self.assertIsNone(first[0]["net_excess_percentage_points"])
        self.benchmark()
        self.journal.observe(self.ledger, observed_at="2026-09-14T20:02:00Z")
        self.assertEqual(self.journal.context(cutoff=MONDAY_CLOSE_CAPTURE), first)
        self.assertIsNotNone(
            self.journal.context(cutoff="2026-09-14T20:02:00Z")[0][
                "net_excess_percentage_points"
            ]
        )
        self.assertEqual(self.journal.summary()["outcome_receipts"], 2)
        self.assertEqual(self.journal.summary()["distinct_closing_observations"], 1)
        with self.journal.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE outcome_receipts SET body='{}'")

    def test_later_observation_cannot_leak_into_earlier_cutoff(self):
        self.fill()
        self.close()
        self.journal.observe(self.ledger, observed_at="2026-09-14T21:00:00Z")
        self.assertEqual(self.journal.context(cutoff=MONDAY_CLOSE_CAPTURE), [])
        self.assertEqual(len(self.journal.context(cutoff="2026-09-14T21:00:00Z")), 1)
        self.assertEqual(
            self.journal.observe(self.ledger, observed_at=SUNDAY)["receipts_added"], 0
        )

    def test_deposits_do_not_become_investment_gains(self):
        self.fill()
        at = "2026-09-14T15:00:00Z"
        self.ledger.deposit(
            "50000", external_id="funding", at=at, quotes=[quote(price="100", at=at)]
        )
        self.close()
        self.journal.observe(self.ledger, observed_at=MONDAY_CLOSE_CAPTURE)
        outcome = self.journal.context(cutoff=MONDAY_CLOSE_CAPTURE)[0]
        self.assertEqual(
            Decimal(outcome["portfolio_return_pct"]),
            Decimal(
                self.ledger.public_state()["performance"]["time_weighted_return_pct"]
            ),
        )
        self.assertLess(Decimal(outcome["portfolio_return_pct"]), 1)

    def test_new_execution_ends_previous_decision_cohort(self):
        self.fill()
        self.close()
        decision_at = "2026-09-14T21:00:00Z"
        session = next_session(decision_at)
        self.ledger.propose(
            "decision-two",
            decided_at=decision_at,
            targets={"AAPL": "0.12"},
            universe_id="universe",
            evidence_refs=["filing-two"],
            expected_open_at=session.opens_at,
            calendar_source=session.source,
        )
        bar = DailyBar(
            symbol="AAPL",
            opens_at=session.opens_at,
            open="105",
            high="120",
            low="100",
            close="110",
            observed_at="2026-09-15T20:01:00Z",
            source="https://example.com/bar",
            source_sha256="b" * 64,
            corporate_actions_checked_through="2026-09-15T20:01:00Z",
        )
        self.ledger.fill_at_next_open(
            "decision-two",
            bars=[bar],
            now="2026-09-15T20:01:00Z",
            market_session=session,
        )
        self.ledger.mark_daily_close(
            [bar],
            observed_at="2026-09-15T20:01:00Z",
            market_session=session_for_day("2026-09-15"),
        )
        self.journal.observe(self.ledger, observed_at="2026-09-15T20:01:00Z")
        rows = self.journal.context(cutoff="2026-09-15T20:01:00Z")
        self.assertEqual(len(rows), 2)
        by_id = {row["decision_id"]: row for row in rows}
        self.assertEqual(by_id["decision-one"]["market_as_of"], "2026-09-14T20:00:00Z")
        self.assertEqual(by_id["decision-two"]["market_as_of"], "2026-09-15T20:00:00Z")
        self.assertFalse(self.journal.summary()["expansion_eligible"])

    def test_account_identity_and_context_bounds_are_fixed(self):
        self.journal.observe(self.ledger, observed_at=SUNDAY)
        with PortfolioLedger(
            self.root / "other.sqlite", created_at="2026-09-12T15:00:00Z"
        ) as other:
            with self.assertRaises(ValueError):
                self.journal.observe(other, observed_at=SUNDAY)
        with self.assertRaises(ValueError):
            self.journal.context(cutoff=SUNDAY, limit=100)

    def test_frozen_policy_and_evidence_provenance_cannot_change_or_leak_backwards(
        self,
    ):
        decided = "2026-09-13T15:01:00Z"
        session = next_session(decided)
        self.ledger.propose(
            "epoch:decision",
            decided_at=decided,
            targets={"AAPL": "0.1"},
            universe_id="universe",
            evidence_refs=["filing"],
            supersedes="decision-one",
            expected_open_at=session.opens_at,
            calendar_source=session.source,
        )
        self.fill()
        self.close()
        self.journal.observe(self.ledger, observed_at=MONDAY_CLOSE_CAPTURE)
        options = {
            "run_id": "epoch",
            "evidence_cutoff": SUNDAY,
            "evidence_sha256": "c" * 64,
            "policy": {"version": 0, "name": "memory_3", "memory_limit": 3},
            "observed_at": "2026-09-14T20:02:00Z",
        }
        self.assertTrue(self.journal.bind_context("epoch:decision", **options))
        self.assertTrue(self.journal.bind_context("epoch:decision", **options))
        self.assertIsNone(
            self.journal.context(cutoff=MONDAY_CLOSE_CAPTURE)[0]["research_context"]
        )
        context = self.journal.context(cutoff=options["observed_at"])[0][
            "research_context"
        ]
        self.assertEqual(context["research_policy"], options["policy"])
        self.assertEqual(context["evidence_cutoff"], SUNDAY)
        with self.assertRaises(ValueError):
            self.journal.bind_context(
                "epoch:decision", **{**options, "evidence_sha256": "d" * 64}
            )
        with self.assertRaises(ValueError):
            self.journal.bind_context(
                "epoch:decision", **{**options, "evidence_cutoff": MONDAY_CLOSE_CAPTURE}
            )


if __name__ == "__main__":
    unittest.main()

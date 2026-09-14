"""Actual paper losses survive failed review epochs; no network or paid calls."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from portfolio_runtime.ledger import PortfolioLedger
from portfolio_runtime.provider import canonical
from portfolio_runtime.research import Research, critic_packet, grade_result
from test_runtime_runner import answer
from portfolio_runtime.service import stamp
import test_runtime_service as service_fixtures


class OutcomeReviewRetryTests(unittest.TestCase):
    # Reuse the real service/market fixtures without inheriting their test suite.
    tearDown = service_fixtures.ServiceTests.tearDown
    service = service_fixtures.ServiceTests.service
    admit = service_fixtures.ServiceTests.admit
    refresh = service_fixtures.ServiceTests.refresh
    execute = service_fixtures.ServiceTests.execute

    def setUp(self):
        service_fixtures.ServiceTests.setUp(self)
        service_fixtures.ServiceTests.test_new_actual_loss_outcome_unlocks_one_review_but_repeated_receipt_does_not(self)
        self.instance = self.service()
        self.instance.initialize()
        with self.instance.connect() as db:
            row = db.execute("SELECT id,config FROM epochs WHERE status='prepared'").fetchone()
        self.epoch_id, self.epoch = row["id"], json.loads(row["config"])
        self.outcome_id = self.epoch["funding_plan"]["new_outcome_ids"][0]
        self.data = json.loads(Path(self.epoch["evidence_path"]).read_text())
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            self.original_events = ledger.events()

    def finish(self, epoch_id=None, config=None):
        epoch_id, config = epoch_id or self.epoch_id, config or self.epoch
        self.at = config["ends_epoch"]
        self.instance.record_value(epoch_id, config)
        with self.instance.connect() as db:
            db.execute("UPDATE epochs SET status='complete' WHERE id=?", (epoch_id,))

    def review(self, *, config=None, verdict="revise", change=None):
        config = config or self.epoch
        research = Research(Path(config["state_dir"])/"research.sqlite", self.data)
        outcomes = self.instance.outcomes.context(cutoff=stamp(self.at))
        packet = {"task": "allocation", "observed_investment_outcomes": outcomes}
        result = answer(targets=[{"symbol": "AAPL", "weight": "0.1"}])
        proposal = hashlib.sha256(canonical(result).encode()).hexdigest()
        critique = answer()
        critique.update(review_verdict=verdict, proposal_sha256=proposal)
        critic_input = critic_packet(proposal, result, deepcopy(packet))
        grades = [grade_result(result, research.companies, allocation=True),
                  grade_result(critique, research.companies, critic=True, proposal_sha256=proposal)]
        if change:
            change(packet, critic_input, critique, grades)
        research.add("allocation", 0, "allocation", None, "pro_asap", "source", canonical(packet))
        research.add("critic", 0, "portfolio_critic", None, "k3", "source", canonical(critic_input))
        with research.connect() as db:
            for identity, output, grade in (("allocation", result, grades[0]), ("critic", critique, grades[1])):
                db.execute("UPDATE tasks SET status='complete',result=?,grade=? WHERE id=?",
                           (canonical(output), canonical(grade), identity))
        return research

    def receipts(self):
        with self.instance.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM outcome_review_receipts")]

    def test_zero_work_failure_retries_then_exact_revision_is_acknowledged_once(self):
        self.finish()  # An expired epoch with no provider task cannot consume a loss.
        self.assertEqual(self.instance.reviewable_outcomes(), [])
        self.at += self.config["session_seconds"] - 1
        self.assertEqual(self.instance.reviewable_outcomes(), [])
        self.at += 1
        self.assertEqual(self.instance.reviewable_outcomes(), [self.outcome_id])
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        prepared = self.instance.prepare_epoch()
        self.assertIsNotNone(prepared)
        retry_id, retry = prepared
        self.assertEqual(retry["funding_plan"]["new_outcome_ids"], [self.outcome_id])
        # The original reservation remains unchanged; later epochs retain attempts.
        with self.instance.connect() as db:
            self.assertEqual(db.execute("SELECT epoch_id FROM consumed_outcomes WHERE identity=?", (self.outcome_id,)).fetchone()[0], self.epoch_id)
        self.review(config=retry)
        self.finish(retry_id, retry)
        receipt = self.receipts()[0]
        self.assertEqual(receipt["epoch_id"], retry_id)
        self.assertEqual(json.loads(receipt["body"])["review_verdict"], "revise")
        self.at += 8*3600
        self.instance.record_value(retry_id, retry)
        self.assertEqual(self.receipts(), [receipt])
        self.assertEqual(self.instance.reviewable_outcomes(), [])
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            self.assertEqual(ledger.events(), self.original_events)

    def test_preclose_allocation_cannot_acknowledge_a_later_loss(self):
        def change(packet, critic, *_):
            packet["observed_investment_outcomes"] = []
            critic["original_input"] = deepcopy(packet)
        self.review(change=change)
        self.finish()
        self.assertEqual(self.receipts(), [])
        self.at += 3600
        self.assertEqual(self.instance.reviewable_outcomes(), [self.outcome_id])

    def test_failed_source_check_never_acknowledges(self):
        self.review(change=lambda p, c, r, grades: grades[1].update(source_check_passed=False))
        self.finish()
        self.assertEqual(self.receipts(), [])

    def test_wrong_proposal_hash_never_acknowledges(self):
        self.review(change=lambda p, c, result, g: result.update(proposal_sha256="0"*64))
        self.finish()
        self.assertEqual(self.receipts(), [])

    def test_unfinished_critic_and_unknown_usage_do_not_acknowledge(self):
        research = self.review()
        with research.connect() as db:
            db.execute("UPDATE tasks SET status='submitted' WHERE id='critic'")
        self.instance.record_outcome_reviews(self.epoch_id, self.epoch)
        self.assertEqual(self.receipts(), [])
        with research.connect() as db:
            db.execute("UPDATE tasks SET status='complete' WHERE id='critic'")
        with sqlite3.connect(Path(self.epoch["state_dir"])/"requests.sqlite") as db:
            db.execute("CREATE TABLE requests(reserved TEXT,cost TEXT,status TEXT)")
            db.execute("INSERT INTO requests VALUES('1',NULL,'completed')")
        self.instance.record_outcome_reviews(self.epoch_id, self.epoch)
        self.assertEqual(self.receipts(), [])
        with sqlite3.connect(Path(self.epoch["state_dir"])/"requests.sqlite") as db:
            db.execute("UPDATE requests SET cost='0.25'")
        self.instance.record_outcome_reviews(self.epoch_id, self.epoch)
        self.assertEqual(len(self.receipts()), 1)

    def test_critic_without_exact_outcome_context_never_acknowledges(self):
        self.review(change=lambda p, critic, *_: critic["original_input"].update(observed_investment_outcomes=[]))
        self.finish()
        self.assertEqual(self.receipts(), [])

    def test_fabricated_outcome_is_not_accepted_as_feedback(self):
        def change(packet, critic, *_):
            packet["observed_investment_outcomes"][0]["portfolio_return_pct"] = "999.0"
            critic["original_input"] = deepcopy(packet)
        self.review(change=change)
        self.finish()
        self.assertEqual(self.receipts(), [])

    def test_supported_abstention_counts_without_authorizing_a_trade(self):
        self.review(verdict="abstain")
        self.finish()
        self.assertEqual(len(self.receipts()), 1)
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            self.assertEqual(ledger.events(), self.original_events)
        with self.instance.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE outcome_review_receipts SET body='{}'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM outcome_review_receipts")

    def test_completed_review_remains_acknowledged_after_restart(self):
        self.review(verdict="approve")
        self.finish()
        original = self.receipts()
        self.at += 8*3600
        self.instance = self.service()
        self.instance.initialize()
        self.assertEqual(self.receipts(), original)
        self.assertEqual(self.instance.reviewable_outcomes(), [])

    def test_reserved_running_and_unsettled_attempts_do_not_retry(self):
        self.at = self.epoch["ends_epoch"]+86400
        for status in ("prepared", "running", "parked_unsettled", "drained_unsettled"):
            with self.subTest(status=status), self.instance.connect() as db:
                db.execute("UPDATE epochs SET status=? WHERE id=?", (status, self.epoch_id))
            self.assertEqual(self.instance.reviewable_outcomes(), [])

    def test_repeated_failed_review_has_increasing_retry_delay(self):
        self.finish()
        self.at += 3600
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        retry_id, retry = self.instance.prepare_epoch()
        self.finish(retry_id, retry)
        self.at += 3600
        self.assertEqual(self.instance.reviewable_outcomes(), [])
        self.at += 3600
        self.assertEqual(self.instance.reviewable_outcomes(), [self.outcome_id])


if __name__ == "__main__":
    unittest.main()

"""Final compute allocation adversaries on disposable SQLite; no native authority."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest import mock

from league.swarm.daily_compute import DailyAdmissionError, NativeUsageSettlementEvidence, ResourceBound, STATE_KEY
from league.swarm.store import SwarmStore
from league.tests import test_native_paused_budget as pause_tests


class NativeUsageSettlement(unittest.TestCase):
    make_budget = pause_tests.NativePausedBudget.make_budget
    attach = pause_tests.NativePausedBudget.attach
    observation = pause_tests.NativePausedBudget.observation
    document_observation = pause_tests.NativePausedBudget.document_observation
    fence = pause_tests.NativePausedBudget.fence
    pause = pause_tests.NativePausedBudget.pause
    attached_then_elapsed = pause_tests.NativePausedBudget.attached_then_elapsed

    def setUp(self):
        pause_tests.NativePausedBudget.setUp(self)

    def paused(self):
        self.attached_then_elapsed()
        self.pause()

    def allocation(self, amount="0.14", *, source=None, **changes):
        row = self.budget._load()["resources"]["gym"]
        previous = row.get("native_usage")
        start = previous["settled_through"] if previous else row["dispatch_at"]
        end = row["terminal_at"] if row["terminal_at"] is not None else row["native_pause"]["observation"]["received_at"]
        charges = [{"utc_day": "2026-10-04", "actual_usd": amount}]
        # Retained bytes resemble the documented native spend fields. Their
        # synthetic origin is explicit; this test does not authenticate a vendor.
        source = source if source is not None else json.dumps({
            "start_at": start, "end_at": end, "finalized_cost_usd_nanos": int(Decimal(amount) * 1_000_000_000),
            "estimated_active_cost_usd_nanos": 0, "sailboxes": [{"sailbox_id": row["resource_id"],
                "active": False, "finalized_cost_usd_nanos": int(Decimal(amount) * 1_000_000_000)}]}, sort_keys=True)
        document = {"schema": 1, "kind": "native_compute_usage_final_allocation", "scope": self.tariff.scope,
                    "resource_id": row["resource_id"], "invoice_id": "SYNTHETIC-completed-statement-1",
                    "source_document_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "interval_start": start, "interval_end": end, "final": True, "complete": True,
                    "includes_creation_fees": False, "includes_volume_storage": False, "charges": charges, **changes}
        raw = json.dumps(document, sort_keys=True)
        return NativeUsageSettlementEvidence(raw, hashlib.sha256(raw.encode()).hexdigest(), source,
            "SYNTHETIC host review of complete original compute statement; no real invoice authority")

    def settle(self, amount="0.14", **changes):
        self.budget.settle_native_usage("gym", evidence=self.allocation(amount, **changes))

    def events(self):
        return self.store._all("SELECT seq,payload FROM events WHERE kind='swarm.daily_budget' ORDER BY seq")

    def test_final_prefix_replaces_only_matching_pending_upper_and_books_original_day(self):
        self.paused()
        events = self.events()
        self.settle()
        summary = self.budget.summary()
        self.assertEqual(summary["resource_upper_nanos"], 140_000_000)
        self.assertEqual(summary["creation_upper_nanos"], 12_000_000)
        self.assertEqual(summary["conditional_future_daily_upper_nanos"], 0)
        self.assertEqual(self.events()[:-1], events)
        row = self.budget._load()["resources"]["gym"]
        self.assertEqual(row["native_pause"]["retained_usage_nanos"], 280_000_000)
        self.assertEqual(row["native_usage"]["retired_upper_nanos"], 280_000_000)
        self.assertIsNone(row["terminal_at"])
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["total_upper_nanos"], 0)

    def test_raw_source_and_projection_are_both_bound_and_retained(self):
        self.paused()
        evidence = self.allocation()
        self.budget.settle_native_usage("gym", evidence=evidence)
        record = self.budget._load()["resources"]["gym"]["native_usage"]["settlements"][0]
        self.assertEqual(record["source_document"], evidence.source_document)
        self.assertEqual(record["document_json"], evidence.document_json)
        self.assertEqual(record["source_document_sha256"], hashlib.sha256(evidence.source_document.encode()).hexdigest())
        for changes in ({"document_sha256": "0" * 64}, {"source_document": "changed"},
                        {"source_document": ""}, {"source_document": "x" * (1024 * 1024 + 1)}):
            with self.subTest(changes=list(changes)), self.assertRaises(DailyAdmissionError): replace(evidence, **changes)

    def test_scope_resource_and_closed_prefix_cannot_be_substituted(self):
        self.paused()
        for changes in ({"scope": "other-scope"}, {"resource_id": "sb_other"},
                        {"interval_start": self.start}, {"interval_end": self.clock() + 1}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError): self.settle(**changes)
        self.assertIsNone(self.budget._load()["resources"]["gym"].get("native_usage"))

    def test_nonfinal_partial_fee_storage_and_sampled_spend_are_not_final_allocations(self):
        self.paused()
        for changes in ({"final": False}, {"final": 1}, {"complete": False}, {"schema": True},
                        {"includes_creation_fees": True}, {"includes_volume_storage": True},
                        {"kind": "estimated_native_spend"}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError): self.allocation(**changes)
        raw = '{"estimated_active_cost_usd_nanos":0,"finalized_cost_usd_nanos":140000000}'
        with self.assertRaises(DailyAdmissionError):
            NativeUsageSettlementEvidence(raw, hashlib.sha256(raw.encode()).hexdigest(), raw, "SYNTHETIC sample")

    def test_duplicate_or_nonexact_money_or_missing_day_cannot_retire_prefix(self):
        self.paused()
        for charges in ([], [{"utc_day": "2026-10-04", "actual_usd": 0.14}],
                        [{"utc_day": "2026-10-04", "actual_usd": "-0.01"}],
                        [{"utc_day": "2026-10-4", "actual_usd": "0.14"}],
                        [{"utc_day": "2026-10-05", "actual_usd": "0.14"}],
                        [{"utc_day": "2026-10-04", "actual_usd": "0.14"}] * 2):
            with self.subTest(charges=charges), self.assertRaises(DailyAdmissionError): self.allocation(charges=charges)
        evidence = self.allocation()
        raw = evidence.document_json[:-1] + ',"complete":true}'
        with self.assertRaises(DailyAdmissionError):
            replace(evidence, document_json=raw, document_sha256=hashlib.sha256(raw.encode()).hexdigest())

    def test_one_shot_settlement_replay_preserves_exact_original_journal(self):
        self.paused()
        evidence = self.allocation()
        self.budget.settle_native_usage("gym", evidence=evidence)
        original = self.events()
        with self.assertRaises(DailyAdmissionError): self.budget.settle_native_usage("gym", evidence=evidence)
        self.assertEqual(self.events(), original)
        self.assertEqual(self.make_budget().summary()["resource_upper_nanos"], 140_000_000)

    def test_completed_usage_preserves_independent_storage_fees_models_and_historical_unknowns(self):
        volume = ResourceBound("SYNTHETIC-volume", "volume", 0, "0", "0", "128", "0", "SYNTHETIC storage")
        self.attach("volume", volume, "vol_synthetic")
        self.paused()
        self.budget.reserve_inference("original-historical-unknown", "12.00595243", provenance="SYNTHETIC old unresolved hold")
        self.budget.dispatch("original-historical-unknown")
        self.budget.reserve_inference("pending-model", "0.2", provenance="SYNTHETIC separate model invoice")
        self.budget.dispatch("pending-model")
        models = self.budget._load()["inference"]
        self.settle()
        current = self.budget.summary()
        self.assertEqual(current["resource_upper_nanos"], 1_402_592_000)
        self.assertEqual(current["creation_upper_nanos"], 12_000_000)
        self.assertEqual(current["inference_upper_nanos"], 12_205_952_430)
        self.assertEqual(self.budget._load()["inference"], models)
        self.clock.advance(86400)
        next_day = self.budget.summary()
        self.assertEqual(next_day["resource_upper_nanos"], 1_262_592_000)
        self.assertEqual(next_day["inference_upper_nanos"], 12_205_952_430)

    def test_original_prior_day_baseline_remains_separate(self):
        # Genuine baseline events cannot be rewritten to fit a new admission.
        self.paused()
        original = self.budget._load()["baseline"]
        self.settle()
        self.assertEqual(self.budget._load()["baseline"], original)
        self.assertFalse(self.budget.summary()["vendor_actual"])

    def test_late_final_compute_is_booked_to_accrual_day_not_reconciliation_day(self):
        self.paused()
        self.clock.advance(86400)
        self.settle()
        summary = self.budget.summary()
        self.assertEqual(summary["resource_upper_nanos"], 0)
        state = self.budget._load()
        self.assertEqual(self.budget._totals(state, int(self.start // 86400))[0], 140_000_000)
        self.assertEqual(summary["conditional_future_daily_upper_nanos"], 0)

    def test_active_resume_keeps_full_reservation_when_previous_closed_prefix_settles(self):
        self.paused()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC explicit resume")
        self.budget.dispatch_resume("gym", "resume-1")
        self.settle()
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_465_030_400)
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch_resume("gym", "resume-1")

    def test_next_closed_prefix_retires_only_new_cumulative_hold(self):
        self.paused()
        self.settle()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC explicit resume")
        self.budget.dispatch_resume("gym", "resume-1")
        self.clock.advance(1800)
        self.pause("0.56")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 420_000_000)
        self.settle("0.10", invoice_id="SYNTHETIC-completed-statement-2")
        state = self.budget._load()
        self.assertEqual(state["resources"]["gym"]["native_usage"]["retired_upper_nanos"], 560_000_000)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 240_000_000)
        self.assertEqual(self.budget.summary()["conditional_future_daily_upper_nanos"], 0)

    def test_same_statement_identity_cannot_be_reused_for_new_prefix(self):
        self.paused()
        self.settle()
        self.clock.advance(1)
        self.pause("0.28")
        with self.assertRaises(DailyAdmissionError): self.settle("0")
        self.settle("0", invoice_id="SYNTHETIC-distinct-zero-statement")
        self.assertEqual(len(self.budget._load()["resources"]["gym"]["native_usage"]["settlements"]), 2)

    def test_final_terminal_interval_can_reconcile_resumed_usage_without_deleting_original_pause(self):
        self.paused()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC explicit resume")
        self.budget.dispatch_resume("gym", "resume-1")
        self.clock.advance(1800)
        self.budget.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status="terminated",
                                      provenance="SYNTHETIC genuine terminal receipt")
        self.settle("0.20")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 200_000_000)
        row = self.budget._load()["resources"]["gym"]
        self.assertEqual(row["native_pause"]["retained_usage_nanos"], 280_000_000)
        self.assertEqual(row["native_usage"]["retired_upper_nanos"], 557_604_800)
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 0)

    def test_greater_final_statement_books_real_charge_and_durably_closes_paid_scope(self):
        self.paused()
        self.budget.reserve_inference("unsent-model", "0.2", provenance="SYNTHETIC original unsent model")
        evidence = self.allocation("0.281")
        with self.assertRaises(DailyAdmissionError): self.budget.settle_native_usage("gym", evidence=evidence)
        state = self.make_budget()._load()
        self.assertTrue(state["breached"])
        self.assertEqual(self.budget._totals(state, int(self.start // 86400))[0], 281_000_000)
        self.assertEqual([json.loads(e["payload"])["action"] for e in self.events()[-2:]],
                         ["scope_breached", "native_usage_settled"])
        with self.assertRaises(DailyAdmissionError): self.make_budget().dispatch("unsent-model")
        with self.assertRaises(DailyAdmissionError): self.make_budget().reserve_inference("new-model", "0.01", provenance="SYNTHETIC")
        self.clock.advance(86400)
        self.assertEqual(self.budget._totals(self.make_budget()._load(), int(self.clock() // 86400))[0], 0)
        self.assertEqual(state["inference"]["unsent-model"]["max_nanos"], 200_000_000)

    def test_reconciliation_works_after_paid_dispatch_withdrawal_without_reopening_it(self):
        self.paused()
        self.budget.reserve_inference("unsent-model", "0.2", provenance="SYNTHETIC unsent model")
        withdrawn = self.make_budget(inventory=replace(self.inventory, exclusive_writer=False))
        with self.assertRaises(DailyAdmissionError): withdrawn.dispatch("unsent-model")
        withdrawn.settle_native_usage("gym", evidence=self.allocation())
        self.assertEqual(withdrawn._load()["resources"]["gym"]["native_usage"]["retired_upper_nanos"], 280_000_000)
        with self.assertRaises(DailyAdmissionError): withdrawn.dispatch("unsent-model")

    def test_cache_cannot_forge_a_retired_prefix_or_reduce_actual_usage(self):
        self.paused()
        self.settle()
        state = self.store.get(STATE_KEY)
        state["resources"]["gym"]["native_usage"]["retired_upper_nanos"] = 100_000_000_000
        self.store.put(STATE_KEY, state)
        with self.assertRaises(DailyAdmissionError): self.make_budget().summary()

    def test_failed_cache_write_rolls_back_one_shot_settlement_and_original_hold(self):
        self.paused()
        original = self.events()
        with mock.patch.object(self.store, "put", side_effect=RuntimeError("synthetic disk failure")):
            with self.assertRaises(RuntimeError): self.settle()
        self.assertEqual(self.events(), original)
        self.assertEqual(self.make_budget().summary()["resource_upper_nanos"], 280_000_000)
        self.settle()

    def test_greater_statement_and_breach_are_one_atomic_transaction(self):
        self.paused()
        original = self.events()
        real_put, count = self.store.put, 0
        def fail_second(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("synthetic second cache write failure")
            return real_put(*args)
        with mock.patch.object(self.store, "put", side_effect=fail_second):
            with self.assertRaises(RuntimeError): self.settle("0.281")
        self.assertEqual(self.events(), original)
        self.assertFalse(self.make_budget()._load()["breached"])
        with self.assertRaises(DailyAdmissionError): self.settle("0.281")
        self.assertTrue(self.make_budget()._load()["breached"])

    def test_concurrent_readers_consume_exactly_one_original_settlement(self):
        self.paused()
        evidence = self.allocation()
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        budgets = [self.budget, self.make_budget(store=other)]
        barrier, results = threading.Barrier(2), []
        def worker(budget):
            barrier.wait()
            try:
                budget.settle_native_usage("gym", evidence=evidence)
                results.append("accepted")
            except DailyAdmissionError:
                results.append("refused")
        threads = [threading.Thread(target=worker, args=(b,)) for b in budgets]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results), ["accepted", "refused"])
        self.assertEqual(len(self.make_budget()._load()["resources"]["gym"]["native_usage"]["settlements"]), 1)

    def test_utc_midnight_allocation_keeps_zero_days_explicit_and_costs_separate(self):
        self.clock.t = self.start + 23 * 3600
        self.attach()
        self.clock.advance(2 * 3600)
        self.pause("1.12")
        for charges in ([{"utc_day": "2026-10-04", "actual_usd": "0.14"}],
                        [{"utc_day": "2026-10-05", "actual_usd": "0"}]):
            with self.assertRaises(DailyAdmissionError): self.allocation(charges=charges)
        evidence = self.allocation(charges=[{"utc_day": "2026-10-04", "actual_usd": "0.14"},
                                          {"utc_day": "2026-10-05", "actual_usd": "0"}])
        self.budget.settle_native_usage("gym", evidence=evidence)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 0)
        self.assertEqual(self.budget._totals(self.budget._load(), int(self.start // 86400))[0], 140_000_000)

    def test_exact_day_boundary_does_not_require_a_day_outside_the_interval(self):
        self.clock.t = self.start + 23 * 3600
        self.attach()
        self.clock.advance(3600)
        self.pause("0.56")
        self.settle("0.14")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 0)

    def test_missing_resource_or_unpaused_creation_is_not_a_final_compute_prefix(self):
        self.paused()
        evidence = self.allocation()
        with self.assertRaises(DailyAdmissionError): self.budget.settle_native_usage("missing", evidence=evidence)
        self.budget.reserve_resource("never-created", self.controller)
        self.budget.dispatch("never-created")
        with self.assertRaises(DailyAdmissionError): self.budget.settle_native_usage("never-created", evidence=evidence)


if __name__ == "__main__":
    unittest.main()

"""Whole UTC-day reservations; only temporary SQLite, fake clocks, and synthetic evidence."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from league.swarm.daily_compute import (
    DailyAdmissionError, DailyBudget, DayCostEvidence, InventoryEvidence, ResourceBound, TariffEvidence, STATE_KEY,
)
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock


class DailyComputeBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.start = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc).timestamp()
        self.clock = Clock(self.start + 10 * 3600)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.tariff = TariffEvidence(
            "synthetic-exclusive-research", "0.0150012", "0.008", "0.0007", "0.000411",
            self.start, self.start + 365 * 86400, "synthetic day tariff certificate; not a production Sail guarantee")
        self.inventory = InventoryEvidence(
            self.tariff.scope, (), (), True, True, False, self.start,
            self.tariff.valid_until, "synthetic exhaustive scope inventory and sole writer")
        self.gym = ResourceBound("synthetic-8cpu-32ram-256disk", "gym", 8, "32", "256", "0", "0.012",
                                 "synthetic hard checkpoint ceilings, including large-size creation")
        self.controller = ResourceBound("synthetic-small-controller", "controller", 1, "16", "32", "0", "0.005",
                                        "synthetic small controller hard ceilings")
        self.budget = self.make_budget()
        self.prior = DayCostEvidence(self.tariff.scope, "2026-10-04", "0", "synthetic complete pre-gate current-day cost inventory")
        self.budget.initialize(self.prior)

    def make_budget(self, *, store=None, tariff=None, inventory=None, cap="25"):
        return DailyBudget(store or self.store, tariff or self.tariff, inventory or self.inventory, daily_cap_usd=cap)

    def attach(self, key="gym", bound=None, resource_id="sb_synthetic_gym"):
        bound = bound or self.gym
        self.budget.reserve_resource(key, bound)
        self.budget.dispatch(key)
        self.budget.attach(key, resource_id, created_at=self.clock(), observed_bound=bound,
                           provenance="synthetic authoritative GET")

    def test_actual_resource_tariff_bound_is_not_workload_estimate(self):
        self.budget.reserve_resource("gym", self.gym)
        summary = self.budget.summary()
        self.assertEqual(summary["resource_upper_nanos"], 13_325_030_400)
        self.assertEqual(summary["creation_upper_nanos"], 12_000_000)
        self.assertEqual(summary["total_upper_usd"], "13.3370304")
        self.assertFalse(summary["vendor_actual"])

    def test_controller_gym_creation_and_inference_share_one_25_dollar_cap(self):
        self.budget.reserve_resource("controller", self.controller)
        self.budget.reserve_resource("gym", self.gym)
        self.budget.reserve_inference("all-meter-inference", "7.68", provenance="synthetic maximum token bill")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "24.9916592")
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_inference("another-call", "0.008340801", provenance="synthetic maximum token bill")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "24.9916592")

    def test_second_large_worker_is_refused_before_dispatch(self):
        self.budget.reserve_resource("controller", self.controller)
        self.budget.reserve_resource("gym", self.gym)
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("gate", replace(self.gym, kind="gate"))
        with self.assertRaises(DailyAdmissionError):
            self.budget.dispatch("gate")

    def test_lost_post_permanently_consumes_its_dispatch_slot(self):
        self.budget.reserve_resource("lost-create", self.gym)
        self.budget.dispatch("lost-create")
        # No attach: the POST could have created a resource even though no reply arrived.
        with self.assertRaises(DailyAdmissionError):
            self.budget.dispatch("lost-create")
        with self.assertRaises(DailyAdmissionError):
            self.budget.cancel_unsent("lost-create")
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("replacement", self.gym)
        self.clock.advance(30 * 86400)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3370304")

    def test_lost_post_creation_fee_carries_until_definitive_creation_day(self):
        self.budget.reserve_resource("delayed-create", self.gym)
        self.budget.dispatch("delayed-create")
        self.clock.advance(3 * 86400)
        self.assertEqual(self.budget.summary()["creation_upper_nanos"], 12_000_000)
        self.budget.attach("delayed-create", "sb_delayed", created_at=self.clock(), observed_bound=self.gym,
                           provenance="synthetic provider creation time")
        self.assertEqual(self.budget.summary()["creation_upper_nanos"], 12_000_000)
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["creation_upper_nanos"], 0)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_325_030_400)

    def test_midnight_and_long_controller_disconnect_do_not_release_resource(self):
        self.clock.advance(self.start + 86399 - self.clock())
        self.attach()
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3370304")
        self.clock.advance(2)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3250304")
        self.clock.advance(120 * 86400)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3250304")

    def test_resource_ttl_sleep_and_transitional_stop_never_release(self):
        self.attach()
        for status in ("sleeping", "paused", "terminating", "expired", "failed"):
            with self.subTest(status=status), self.assertRaises(DailyAdmissionError):
                self.budget.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status=status,
                                              provenance="synthetic provider state")
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_325_030_400)

    def test_terminal_state_releases_only_future_days_and_retains_full_observation_day(self):
        self.attach()
        self.budget.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status="terminated",
                                      provenance="synthetic permanent provider terminal state")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3370304")
        self.assertEqual(self.budget.summary()["conditional_future_daily_upper_nanos"], 0)
        # It cannot buy a second full-day large worker on the same day.
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("replacement", self.gym)
        self.clock.advance(86400)
        self.budget.reserve_resource("replacement", self.gym)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "13.3370304")

    def test_volume_exists_and_bills_after_worker_terminates(self):
        volume = ResourceBound("synthetic-128gib-volume", "volume", 0, "0", "0", "128", "0",
                               "synthetic independently charged persistent volume")
        self.attach()
        self.attach("volume", volume, "vol_synthetic")
        self.budget.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status="terminated",
                                      provenance="synthetic permanent terminal state")
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "1.262592")
        with self.assertRaises(DailyAdmissionError):
            self.budget.terminal_observed("volume", "vol_synthetic", observed_at=self.clock(), status="terminated",
                                          provenance="synthetic volume state")
        self.budget.terminal_observed("volume", "vol_synthetic", observed_at=self.clock(), status="deleted",
                                      provenance="synthetic permanent volume deletion")
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "0")

    def test_attached_volume_cannot_hide_inside_worker_bound(self):
        with self.assertRaises(DailyAdmissionError):
            replace(self.gym, volume_gib="128")

    def test_pending_inference_retains_its_maximum_on_all_possible_future_days(self):
        self.budget.reserve_inference("lost-model", "12", provenance="synthetic provider token maximum")
        self.budget.dispatch("lost-model")
        self.clock.advance(4 * 86400)
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], 12_000_000_000)
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("gym", self.gym)
        self.budget.settle_inference("lost-model", accrued_day="2026-10-04", actual_usd="11",
                                     provenance="synthetic authoritative terminal receipt and UTC charge day")
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], 0)
        self.budget.reserve_resource("gym", self.gym)

    def test_terminal_inference_receipt_replaces_upper_bound_without_double_counting(self):
        self.budget.reserve_inference("model", "5", provenance="synthetic token maximum")
        self.budget.dispatch("model")
        self.budget.settle_inference("model", accrued_day="2026-10-04", actual_usd="3.1",
                                     provenance="synthetic terminal bill")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "3.1")
        with self.assertRaises(DailyAdmissionError):
            self.budget.settle_inference("model", accrued_day="2026-10-04", actual_usd="3",
                                         provenance="synthetic repeated terminal bill")

    def test_excess_invoice_or_wrong_charge_day_cannot_release_inference(self):
        self.budget.reserve_inference("model", "1", provenance="synthetic token maximum")
        self.budget.dispatch("model")
        for day, usd in (("2026-10-03", "0.5"), ("2026-10-05", "0.5")):
            with self.subTest(day=day, usd=usd), self.assertRaises(DailyAdmissionError):
                self.budget.settle_inference("model", accrued_day=day, actual_usd=usd,
                                             provenance="synthetic mismatched bill")
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], 1_000_000_000)
        with self.assertRaises(DailyAdmissionError):
            self.budget.settle_inference("model", accrued_day="2026-10-04", actual_usd="1.01",
                                         provenance="synthetic maximum-exceeding authoritative bill")
        with self.assertRaises(DailyAdmissionError): self.budget.summary()
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_resource("gym", self.gym)

    def test_unsent_can_be_canceled_but_its_identity_cannot_be_reused(self):
        self.budget.reserve_resource("unsent", self.gym)
        self.budget.cancel_unsent("unsent")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "0")
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("unsent", self.gym)
        with self.assertRaises(DailyAdmissionError):
            self.budget.dispatch("unsent")

    def test_atomic_compute_inference_race_has_one_admission(self):
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        peer = self.make_budget(store=other)
        barrier, results = threading.Barrier(2), []
        def run(operation):
            barrier.wait()
            try:
                operation()
                results.append("admitted")
            except DailyAdmissionError:
                results.append("refused")
        threads = [threading.Thread(target=run, args=(operation,)) for operation in (
            lambda: self.budget.reserve_resource("gym", self.gym),
            lambda: peer.reserve_inference("model", "12", provenance="synthetic maximum token bill"))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["admitted", "refused"])
        self.assertTrue(self.budget.summary()["within_cap"])

    def test_dispatch_race_cannot_create_two_resources_on_one_slot(self):
        self.budget.reserve_resource("gym", self.gym)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        peer = self.make_budget(store=other)
        barrier, results = threading.Barrier(2), []
        def run(budget):
            barrier.wait()
            try:
                budget.dispatch("gym")
                results.append("dispatched")
            except DailyAdmissionError:
                results.append("refused")
        threads = [threading.Thread(target=run, args=(b,)) for b in (self.budget, peer)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["dispatched", "refused"])

    def test_restart_retains_all_pending_obligations(self):
        self.budget.reserve_resource("gym", self.gym)
        self.budget.dispatch("gym")
        self.budget.reserve_inference("model", "2", provenance="synthetic token maximum")
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        self.clock.advance(86400)
        peer = self.make_budget(store=other)
        self.assertEqual(peer.summary()["total_upper_usd"], "15.3370304")
        with self.assertRaises(DailyAdmissionError): peer.dispatch("gym")

    def test_cache_loss_and_forged_release_fail_closed_against_receipts(self):
        self.budget.reserve_resource("gym", self.gym)
        real = self.store.get(STATE_KEY)
        forged = json.loads(json.dumps(real))
        forged["resources"]["gym"]["canceled"] = True
        self.store.put(STATE_KEY, forged)
        with self.assertRaises(DailyAdmissionError): self.budget.summary()
        self.store.put(STATE_KEY, real)
        self.store._exec("DELETE FROM kv WHERE key=?", (STATE_KEY,))
        with self.assertRaises(DailyAdmissionError): self.budget.summary()
        with self.assertRaises(DailyAdmissionError): self.budget.initialize(self.prior)

    def test_immutable_receipts_cannot_be_changed_or_deleted(self):
        import sqlite3
        self.budget.reserve_resource("gym", self.gym)
        for sql in ("DELETE FROM events WHERE kind='swarm.daily_budget'",
                    "UPDATE events SET payload='{}' WHERE kind='swarm.daily_budget'"):
            with self.assertRaises(sqlite3.IntegrityError): self.store._exec(sql)

    def test_unknown_legacy_partial_inventory_and_shared_writer_block_every_paid_admission(self):
        for inventory in (replace(self.inventory, complete=False), replace(self.inventory, exclusive_writer=False),
                          replace(self.inventory, unknown_obligations=True),
                          replace(self.inventory, resource_ids=("sb_unpriced_legacy",)),
                          replace(self.inventory, model_keys=("unpriced-old-model",))):
            budget = self.make_budget(inventory=inventory)
            with self.subTest(inventory=inventory), self.assertRaises(DailyAdmissionError):
                budget.reserve_inference("paid", "0.01", provenance="synthetic maximum bill")
            with self.assertRaises(DailyAdmissionError): budget.reserve_resource("paid", self.controller)

    def test_complete_inventory_may_bind_existing_tracked_resources_without_releasing_missing_ones(self):
        self.attach()
        inventory = replace(self.inventory, resource_ids=("sb_synthetic_gym",))
        self.assertTrue(self.make_budget(inventory=inventory).summary()["within_cap"])
        # An absent row might be a stale list. It cannot imply termination.
        self.clock.advance(86400)
        self.assertEqual(self.make_budget().summary()["resource_upper_nanos"], 13_325_030_400)

    def test_stale_tariff_blocks_paid_calls_without_claiming_an_unlimited_price_lock(self):
        self.attach()
        tariff = replace(self.tariff, valid_until=self.start + 86400)
        certified = self.make_budget(tariff=tariff)
        self.assertTrue(certified.summary()["within_cap"])
        self.clock.advance(86400)
        with self.assertRaises(DailyAdmissionError): certified.summary()
        with self.assertRaises(DailyAdmissionError):
            certified.reserve_inference("paid", "0.01", provenance="synthetic maximum bill")
        # Reconciliation is permitted even when admission evidence is stale.
        certified.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status="terminated",
                                    provenance="synthetic permanent terminal evidence")

    def test_tariff_does_not_cover_whole_day_when_only_part_day_is_certified(self):
        tariff = replace(self.tariff, valid_from=self.start + 1)
        with self.assertRaises(DailyAdmissionError): self.make_budget(tariff=tariff).summary()

    def test_new_day_rate_increase_is_priced_and_can_close_admission(self):
        self.attach()
        tariff = replace(self.tariff, memory_gib_usd_hour="0.030")
        summary = self.make_budget(tariff=tariff).summary()
        self.assertFalse(summary["within_cap"])
        with self.assertRaises(DailyAdmissionError):
            self.make_budget(tariff=tariff).reserve_inference("paid", "0.01", provenance="synthetic maximum bill")

    def test_changed_scope_or_ceiling_does_not_reinitialize_existing_budget(self):
        with self.assertRaises(DailyAdmissionError): self.make_budget(cap="24").summary()
        with self.assertRaises(DailyAdmissionError): self.make_budget(cap="25.000000001")
        other_scope = replace(self.tariff, scope="different-scope")
        other_inventory = replace(self.inventory, scope="different-scope")
        with self.assertRaises(DailyAdmissionError):
            self.make_budget(tariff=other_scope, inventory=other_inventory).summary()

    def test_observed_resources_must_fit_original_bound_and_unique_identity(self):
        self.budget.reserve_resource("gym", self.gym)
        self.budget.dispatch("gym")
        self.budget.attach("gym", "sb_gym", created_at=self.clock(), observed_bound=self.gym,
                           provenance="synthetic matching metadata")
        self.budget.reserve_resource("controller", self.controller)
        self.budget.dispatch("controller")
        with self.assertRaises(DailyAdmissionError):
            self.budget.attach("controller", "sb_gym", created_at=self.clock(), observed_bound=self.controller,
                               provenance="synthetic duplicated provider identity")

    def test_incompatible_resource_metadata_persists_a_breach_across_restart(self):
        self.budget.reserve_resource("gym", self.gym)
        self.budget.dispatch("gym")
        with self.assertRaises(DailyAdmissionError):
            self.budget.attach("gym", "sb_gym", created_at=self.clock(), observed_bound=replace(self.gym, memory_gib="64"),
                               provenance="synthetic incompatible resource metadata")
        peer = self.make_budget()
        with self.assertRaises(DailyAdmissionError): peer.summary()
        with self.assertRaises(DailyAdmissionError):
            peer.reserve_inference("paid", "0.01", provenance="synthetic token maximum")

    def test_initialization_requires_prior_cost_evidence_and_preserves_old_research_spend(self):
        with self.assertRaises(DailyAdmissionError): self.budget.initialize(None)
        root = self.root / "other-empty-scope"
        store = SwarmStore(root, clock=self.clock)
        self.addCleanup(store.close)
        budget = self.make_budget(store=store)
        prior = replace(self.prior, upper_usd="1.19")
        budget.initialize(prior)
        budget.reserve_resource("controller", self.controller)
        budget.reserve_resource("gym", self.gym)
        with self.assertRaises(DailyAdmissionError):
            budget.reserve_inference("7.68-spend", "7.68", provenance="synthetic token maximum")
        self.assertEqual(budget.summary()["prior_cost_upper_nanos"], 1_190_000_000)
        self.clock.advance(86400)
        self.assertEqual(budget.summary()["prior_cost_upper_nanos"], 0)

    def test_nanodollar_rounding_never_fits_a_subnanodollar_overrun(self):
        self.budget.reserve_inference("most", "24.999999999", provenance="synthetic maximum bill")
        self.budget.reserve_inference("tiny", "0.00000000001", provenance="synthetic positive maximum bill")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "25")
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_inference("one-more", "0.00000000001", provenance="synthetic positive maximum bill")

    def test_exact_decimal_evidence_is_serialized_without_binary_float_conversion(self):
        from decimal import Decimal
        gym = replace(self.gym, memory_gib=Decimal("32"), creation_fee_usd=Decimal("0.012"))
        tariff = replace(self.tariff, vcpu_usd_hour=Decimal("0.0150012"))
        self.make_budget(tariff=tariff).reserve_resource("gym", gym)
        self.assertEqual(self.budget.summary()["total_upper_nanos"], 13_337_030_400)

    def test_invalid_money_provenance_and_time_are_not_free_capacity(self):
        for value in (True, 0.2, "NaN", "Infinity", "-1", "0", "0.0000000000001"):
            with self.subTest(value=value), self.assertRaises(DailyAdmissionError):
                self.budget.reserve_inference("invalid", value, provenance="synthetic maximum bill")
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_resource("invalid", replace(self.gym, provenance=""))
        self.budget.reserve_resource("gym", self.gym)
        self.clock.advance(-1)
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch("gym")

    def test_receipt_transaction_failure_rolls_back_both_admission_and_cache(self):
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("synthetic disk failure")):
            with self.assertRaises(RuntimeError): self.budget.reserve_resource("gym", self.gym)
        self.assertEqual(self.budget.summary()["total_upper_usd"], "0")
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch("gym")


if __name__ == "__main__":
    unittest.main()

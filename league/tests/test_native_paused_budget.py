"""Adversarial synthetic receipts only: no actual API, resource or billing authority."""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
from dataclasses import replace
from unittest import mock

from league.swarm.daily_compute import (
    DailyAdmissionError, NativePausedEvidence, ResumeFenceEvidence, ResourceBound, STATE_KEY,
)
from league.swarm.store import SwarmStore
from league.tests import test_daily_compute_budget as daily_tests


class NativePausedBudget(unittest.TestCase):
    make_budget = daily_tests.DailyComputeBudget.make_budget
    attach = daily_tests.DailyComputeBudget.attach

    def setUp(self):
        daily_tests.DailyComputeBudget.setUp(self)

    def observation(self, resource_id="sb_synthetic_gym", **changes):
        body = json.dumps({"sailbox_id": resource_id, "status": "paused", "vcpu_count": 8,
                           "memory_mib": 32768, "state_disk_size_gib": 256, "volume_mounts": [],
                           "unknown_future_field": "native responses can grow"}, sort_keys=True)
        return NativePausedEvidence(**{
            "scope": self.tariff.scope, "resource_id": resource_id, "method": "GET",
            "url": "https://sailbox-api.sailresearch.com/v1/sailboxes/" + resource_id,
            "started_at": self.clock(), "received_at": self.clock(), "http_status": 200,
            "document_json": body, "document_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "provenance": "SYNTHETIC native GET transport capture, not actual Sail evidence", **changes})

    def document_observation(self, **changes):
        observation = self.observation()
        body = json.dumps({**json.loads(observation.document_json), **changes})
        return replace(observation, document_json=body, document_sha256=hashlib.sha256(body.encode()).hexdigest())

    def fence(self, resource_id="sb_synthetic_gym", **changes):
        return ResumeFenceEvidence(**{
            "scope": self.tariff.scope, "resource_id": resource_id, "fence_id": "synthetic-native-resume-fence",
            "writer_ids": ("synthetic-controller", "synthetic-nightly", "synthetic-direct-operator"),
            "complete": True, "exclusive_writer": True, "pending_resume_requests": (),
            "effective_at": self.start, "valid_until": self.start + 3 * 86400,
            "enforcement_sha256": "d" * 64,
            "provenance": "SYNTHETIC reviewed enforcement; a local declaration is not production proof", **changes})

    def pause(self, retained="0.28", **changes):
        self.budget.paused_observed("gym", observation=self.observation(), fence=self.fence(),
                                    retained_native_usage_upper_usd=retained,
                                    usage_provenance="SYNTHETIC accrued plus larger pending billing bound", **changes)

    def attached_then_elapsed(self):
        self.attach()
        self.clock.advance(1800)

    def test_completed_pause_retains_elapsed_pending_cost_fee_and_original_ledger(self):
        self.attached_then_elapsed()
        original_events = self.store._all("SELECT seq,payload FROM events WHERE kind='swarm.daily_budget' ORDER BY seq")
        self.pause()
        summary = self.budget.summary()
        self.assertEqual(summary["resource_upper_nanos"], 280_000_000)
        self.assertEqual(summary["creation_upper_nanos"], 12_000_000)
        self.assertEqual(summary["conditional_future_daily_upper_nanos"], 280_000_000)
        self.assertFalse(summary["vendor_actual"])
        self.assertEqual(self.store._all("SELECT seq,payload FROM events WHERE kind='swarm.daily_budget' ORDER BY seq")[:-1], original_events)
        original = self.store.get(STATE_KEY)
        row = original["resources"]["gym"]
        self.assertEqual(row["resource_id"], "sb_synthetic_gym")
        self.assertIsNone(row["terminal_at"])
        self.assertEqual(original["scope"], self.tariff.scope)
        self.assertEqual(original["cap_nanos"], 25_000_000_000)
        self.assertEqual(row["native_pause"]["retained_usage_nanos"], 280_000_000)

    def test_original_unsettled_model_and_historical_hold_are_preserved(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_inference("original-historical-unknown", "12.00595243",
                                      provenance="SYNTHETIC original historical unknown hold, not today's expense")
        self.budget.dispatch("original-historical-unknown")
        self.budget.reserve_inference("pending-model", "0.2", provenance="SYNTHETIC pending invoice upper")
        self.budget.dispatch("pending-model")
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], 12_205_952_430)
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["inference_upper_nanos"], 12_205_952_430)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 280_000_000)

    def test_partial_day_future_fence_expiry_is_reserved_before_it_happens(self):
        self.attached_then_elapsed()
        fence = self.fence(valid_until=self.start + 12 * 3600)
        self.budget.paused_observed("gym", observation=self.observation(), fence=fence,
                                    retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC pending usage")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 6_942_515_200)
        # Future expiry does not get represented as an everlasting native fence.
        self.assertGreater(self.budget.summary()["conditional_future_daily_upper_nanos"], 13_325_030_400)
        self.clock.advance(3 * 3600)
        with self.assertRaises(DailyAdmissionError): self.budget.summary()
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_inference("after-expiry", "0.01", provenance="SYNTHETIC bill")
        # Expiry also restores its compute liability in the same durable ledger.
        totals = self.budget._totals(self.budget._load(), int(self.clock() // 86400))
        self.assertEqual(totals[0], 6_942_515_200)

    def test_reobserved_pause_cannot_erase_an_unfenced_running_gap(self):
        self.attached_then_elapsed()
        self.budget.paused_observed("gym", observation=self.observation(), fence=self.fence(valid_until=self.clock() + 60),
                                    retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC pending usage")
        self.clock.advance(3660)
        with self.assertRaises(DailyAdmissionError): self.pause()
        self.pause("0.84")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 840_000_000)

    def test_acceptance_post_sleep_ttl_and_wrong_native_route_never_prove_pause(self):
        self.attached_then_elapsed()
        for changes in ({"method": "POST"}, {"http_status": 202}, {"http_status": True},
                        {"url": "https://example.test/v1/sailboxes/sb_synthetic_gym"},
                        {"url": "https://sailbox-api.sailresearch.com/v1/sailboxes/sb_synthetic_gym/pause"},
                        {"url": "https://sailbox-api.sailresearch.com/v1/sailboxes/sb_synthetic_gym?status=paused"}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError): self.observation(**changes)
        for status in ("sleeping", "pausing", "running", "expired", "terminated", "failed"):
            with self.subTest(status=status), self.assertRaises(DailyAdmissionError): self.document_observation(status=status)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_325_030_400)

    def test_get_byte_hash_duplicate_fields_and_wrong_identity_are_refused(self):
        self.attached_then_elapsed()
        with self.assertRaises(DailyAdmissionError): self.observation(document_sha256="0" * 64)
        with self.assertRaises(DailyAdmissionError): self.document_observation(sailbox_id="sb_foreign")
        raw = '{"sailbox_id":"sb_synthetic_gym","status":"running","status":"paused"}'
        with self.assertRaises(DailyAdmissionError):
            self.observation(document_json=raw, document_sha256=hashlib.sha256(raw.encode()).hexdigest())
        for changes in ({"vcpu_count": True}, {"memory_mib": None}, {"state_disk_size_gib": 0}, {"volume_mounts": None}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError): self.document_observation(**changes)

    def test_false_partial_shared_or_pending_resume_fences_are_refused(self):
        for changes in ({"complete": False}, {"complete": 1}, {"exclusive_writer": False},
                        {"pending_resume_requests": ("old-resume-post",)}, {"writer_ids": ()},
                        {"writer_ids": ("same", "same")}, {"enforcement_sha256": "declaration"}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError): self.fence(**changes)

    def test_fence_must_cover_get_before_request_starts_and_current_reconciliation(self):
        self.attached_then_elapsed()
        observation = self.observation(started_at=self.clock() - 1)
        for fence in (self.fence(effective_at=self.clock()), self.fence(valid_until=self.clock()),
                      self.fence(scope="foreign"), self.fence(resource_id="sb_foreign")):
            with self.subTest(fence=fence), self.assertRaises(DailyAdmissionError):
                self.budget.paused_observed("gym", observation=observation, fence=fence,
                                            retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC usage")
        with self.assertRaises(DailyAdmissionError):
            self.budget.paused_observed("gym", observation=self.observation(received_at=self.clock() + 1),
                                        fence=self.fence(), retained_native_usage_upper_usd="0.28",
                                        usage_provenance="SYNTHETIC usage")

    def test_accrued_and_larger_billing_hold_cannot_be_shrunk_by_pause(self):
        self.attached_then_elapsed()
        for value in ("0", "0.277604799", True, 0.28):
            with self.subTest(value=value), self.assertRaises(DailyAdmissionError): self.pause(value)
        self.pause("1")
        self.clock.advance(1)
        with self.assertRaises(DailyAdmissionError): self.pause("0.99")
        self.pause("1")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 1_000_000_000)

    def test_native_pause_preserves_separately_charged_storage(self):
        volume = ResourceBound("SYNTHETIC-volume", "volume", 0, "0", "0", "128", "0", "SYNTHETIC storage")
        self.attach("volume", volume, "vol_synthetic")
        self.attached_then_elapsed()
        observation = self.document_observation(volume_mounts=[{"volume_id": "vol_synthetic", "mount_path": "/data"}])
        self.budget.paused_observed("gym", observation=observation, fence=self.fence(),
                                    retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC usage")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 1_542_592_000)
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 1_542_592_000)
        with self.assertRaises(DailyAdmissionError):
            self.budget.paused_observed("volume", observation=self.observation("vol_synthetic"),
                                        fence=self.fence("vol_synthetic"), retained_native_usage_upper_usd="1",
                                        usage_provenance="SYNTHETIC storage")

    def test_unaccounted_mount_and_greater_resource_limits_refuse_release(self):
        self.attached_then_elapsed()
        for changes in ({"volume_mounts": [{"volume_id": "vol_unpriced"}]}, {"vcpu_count": 9},
                        {"memory_mib": 65536}, {"state_disk_size_gib": 512}):
            with self.subTest(changes=changes), self.assertRaises(DailyAdmissionError):
                self.budget.paused_observed("gym", observation=self.document_observation(**changes), fence=self.fence(),
                                            retained_native_usage_upper_usd="1", usage_provenance="SYNTHETIC usage")
        with self.assertRaises(DailyAdmissionError): self.make_budget().summary()
        with self.assertRaises(DailyAdmissionError):
            self.make_budget().reserve_inference("ignored-metadata-breach", "0.01", provenance="SYNTHETIC maximum")
        self.assertEqual(self.store.get(STATE_KEY)["resources"]["gym"].get("native_pause"), None)

    def test_lost_create_or_foreign_original_key_cannot_be_reconciled_as_paused(self):
        self.budget.reserve_resource("lost", self.gym)
        self.budget.dispatch("lost")
        for key in ("lost", "missing"):
            with self.subTest(key=key), self.assertRaises(DailyAdmissionError):
                self.budget.paused_observed(key, observation=self.observation(), fence=self.fence(),
                                            retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC usage")

    def test_original_creation_slot_is_not_replayed_for_resume(self):
        self.attached_then_elapsed()
        self.pause()
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch("gym")
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch_resume("gym", "never-reserved")
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC same-ledger resume")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_605_030_400)
        self.budget.dispatch_resume("gym", "resume-1")
        with self.assertRaises(DailyAdmissionError): self.budget.dispatch_resume("gym", "resume-1")
        with self.assertRaises(DailyAdmissionError): self.budget.cancel_resume_unsent("gym", "resume-1")
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_resume("gym", "replacement", provenance="SYNTHETIC lost resume reply")

    def test_same_25_ledger_refuses_resume_when_other_obligations_use_the_room(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_inference("original-pending-model", "12", provenance="SYNTHETIC maximum")
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_resume("gym", "resume-no-room", provenance="SYNTHETIC resume")
        self.assertEqual(self.budget.summary()["total_upper_usd"], "12.292")

    def test_unsent_resume_cancel_restores_pause_but_never_reuses_identity(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-unsent", provenance="SYNTHETIC original reserve")
        self.budget.cancel_resume_unsent("gym", "resume-unsent")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 280_000_000)
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_resume("gym", "resume-unsent", provenance="SYNTHETIC replay")
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_inference("resume-unsent", "1", provenance="SYNTHETIC reused identity")

    def test_resume_lost_reply_retains_running_capacity_over_midnight_and_restart(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-lost", provenance="SYNTHETIC reserve")
        self.budget.dispatch_resume("gym", "resume-lost")
        self.clock.advance(86400)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        peer = self.make_budget(store=other)
        self.assertGreater(peer.summary()["resource_upper_nanos"], 13_605_030_400)
        with self.assertRaises(DailyAdmissionError): peer.dispatch_resume("gym", "resume-lost")

    def test_later_pause_keeps_previously_retained_and_resumed_usage(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC reserve")
        self.budget.dispatch_resume("gym", "resume-1")
        self.clock.advance(1800)
        with self.assertRaises(DailyAdmissionError): self.pause("0.28")
        self.pause("0.56")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 560_000_000)
        with self.assertRaises(DailyAdmissionError): self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC replay")

    def test_terminal_after_resume_preserves_unsettled_post_resume_cost(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC reserve")
        self.budget.dispatch_resume("gym", "resume-1")
        self.clock.advance(1800)
        self.budget.terminal_observed("gym", "sb_synthetic_gym", observed_at=self.clock(), status="terminated",
                                      provenance="SYNTHETIC actual terminal GET")
        self.clock.advance(86400)
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 557_604_800)

    def test_pause_proof_replay_and_cache_forgery_cannot_drop_original_holds(self):
        self.attached_then_elapsed()
        original_observation = self.observation()
        self.pause()
        with self.assertRaises(DailyAdmissionError):
            self.budget.paused_observed("gym", observation=original_observation, fence=self.fence(),
                                        retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC stale readback")
        real = self.store.get(STATE_KEY)
        forged = json.loads(json.dumps(real))
        forged["resources"]["gym"]["native_pause"]["retained_usage_nanos"] = 0
        self.store.put(STATE_KEY, forged)
        with self.assertRaises(DailyAdmissionError): self.budget.summary()

    def test_pause_transaction_failure_preserves_original_full_resource_hold(self):
        self.attached_then_elapsed()
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("SYNTHETIC disk failure")):
            with self.assertRaises(RuntimeError): self.pause()
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 13_325_030_400)

    def test_resume_dispatch_race_consumes_only_one_original_slot(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-race", provenance="SYNTHETIC reserve")
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        peer = self.make_budget(store=other)
        barrier, results = threading.Barrier(2), []
        def dispatch(budget):
            barrier.wait()
            try:
                budget.dispatch_resume("gym", "resume-race")
                results.append("dispatched")
            except DailyAdmissionError:
                results.append("refused")
        threads = [threading.Thread(target=dispatch, args=(budget,)) for budget in (self.budget, peer)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["dispatched", "refused"])

    def test_new_cheaper_rate_does_not_erase_old_unsettled_resume_cost(self):
        self.attached_then_elapsed()
        self.pause()
        self.budget.reserve_resume("gym", "resume-1", provenance="SYNTHETIC reserve")
        self.budget.dispatch_resume("gym", "resume-1")
        self.clock.advance(1800)
        cheaper = replace(self.tariff, vcpu_usd_hour="0.001", memory_gib_usd_hour="0.001", disk_gib_usd_hour="0.0001")
        peer = self.make_budget(tariff=cheaper)
        with self.assertRaises(DailyAdmissionError):
            peer.paused_observed("gym", observation=self.observation(), fence=self.fence(),
                                 retained_native_usage_upper_usd="0.30", usage_provenance="SYNTHETIC lower current price")

    def test_fractional_native_capture_times_round_every_capacity_dimension_up(self):
        self.attach()
        self.clock.advance(1800.123457)
        self.pause("0.28")
        self.assertEqual(self.budget.summary()["resource_upper_nanos"], 280_000_000)
        from league.swarm.daily_compute import _interval_nanos
        # Even a tiny positive interval cannot become a free subnanodollar bill.
        self.assertEqual(_interval_nanos(self.gym, self.tariff, 0, 1e-320), 3)

    def test_renewal_does_not_require_a_future_tariff_when_no_unfenced_time_elapsed(self):
        self.attached_then_elapsed()
        self.pause()
        self.clock.advance(1)
        current_day_only = replace(self.tariff, valid_until=self.start + 86400)
        peer = self.make_budget(tariff=current_day_only)
        peer.paused_observed("gym", observation=self.observation(), fence=self.fence(),
                             retained_native_usage_upper_usd="0.28", usage_provenance="SYNTHETIC unchanged pending usage")
        self.assertEqual(peer.summary()["resource_upper_nanos"], 280_000_000)


if __name__ == "__main__":
    unittest.main()

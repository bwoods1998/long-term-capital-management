"""Conditional compute commitments and uncertain stops, using only fake clocks/clients and SQLite."""
from __future__ import annotations

import copy
import datetime as dt
import math
import tempfile
import threading
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest import mock

from league.ops import budget as B
from league.swarm import compute
from league.swarm.guard import SailGuard
from league.swarm.models import ModelError, ModelRouter
from league.swarm.pool import Box, GymPool
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail
from league.tests.test_swarm_pool import job


class ComputeBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(dt.datetime(2026, 10, 4, 10, tzinfo=dt.timezone.utc).timestamp())
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        B._write_json(self.root / "budget.json", B.compute({"p30_usd": 0, "edge": {"stop": False}, "meters": {
            "sail": {"balance_usd": 500, "fixed_usd_day": 1, "reserve_usd": 37},
            "claude": {"balance_usd": 500, "fixed_usd_day": 0}}}, now=self.clock()))
        self.cfg = copy.deepcopy(DEFAULTS)
        self.cfg["budget"] = {"source": "synthetic", "sail_usd_day": 15.0, "claude_usd_day": 10.0}
        self.image = "sbcp_11111111-aaaa"
        self.bound = compute.ComputeBound(self.image, 0.20, 0.01, 1800, 30, 30, self.clock() + 86400,
                                          "synthetic provider contract; never an assertion about Sail")
        self.cfg["gym"].update(enabled=True, image_checkpoint=self.image, start_boxes=1,
                                compute_bounds={self.image: asdict(self.bound)}, reconcile_seconds=1e9, book_seconds=1)
        self.sail = FakeSail()
        self.pool = self.make_pool()

    def make_pool(self):
        p = GymPool(self.store, self.sail, self.cfg, clock=self.clock, threaded=False,
                    driver_factory=lambda client, box: FakeDriver(client, box))
        p.reconciled_at = self.clock()
        return p

    def reserve(self, key="synthetic", kind="gate"):
        return compute.reserve(self.store, self.cfg, key, self.bound, kind=kind, now=self.clock())

    def box(self):
        self.reserve()
        compute.attach(self.store, "synthetic", "sb_compute")
        box = Box("sb_compute", "gym", self.image, "ready", booked_at=self.clock(),
                  driver=FakeDriver(self.sail, "sb_compute"), roots=("SPY",))
        self.pool.boxes[box.id] = box
        self.store.upsert_box(box.id, kind="gym", version=self.image, state="ready",
                              detail={"cost_cursor": {"awake": True, "booked_at": self.clock(), "estimate": True}})
        return box

    def row(self):
        return self.store.boxes(live=False)[0]

    def admit_model(self, usd, key="model"):
        ModelRouter(self.store, None, settings=self.cfg)._sail_admit(key, usd, kind="sail_model", family=None,
                                                                  profile="synthetic", role="audit")

    def test_missing_provider_bound_never_forks_or_consumes_a_trial(self):
        del self.cfg["gym"]["compute_bounds"]
        queued = self.pool.submit(job())
        self.pool._start_box("gym")
        self.assertEqual(self.sail.forks, [])
        self.assertEqual((queued.attempts, queued.done.is_set(), self.pool.queued()), (0, False, 1))
        self.assertEqual(self.store.get("compute_holds"), None)

    def test_busy_obligation_that_would_exceed_25_dollars_is_refused_before_fork(self):
        self.store.add_spend("sail_model", 14.99)
        self.store.add_spend("claude", 10.0)
        self.pool._start_box("gym")
        self.assertEqual(self.sail.forks, [])
        self.assertAlmostEqual(self.store.spent(["sail_model", "gym_box", "claude"]), 24.99)
        self.assertEqual(compute.remaining(self.store, now=self.clock()), 0)

    def test_hold_exists_before_post_and_documented_lifetime_is_sent(self):
        real = self.sail.from_checkpoint
        seen = []
        def fork(checkpoint, **kw):
            seen.append((compute.remaining(self.store, now=self.clock()), kw["max_lifetime_seconds"]))
            return real(checkpoint, **kw)
        self.sail.from_checkpoint = fork
        self.pool._start_box("gym")
        self.assertEqual(seen, [(self.bound.usd, self.bound.max_lifetime_seconds)])
        self.assertIsNotNone(next(iter(self.store.get("compute_holds").values()))["box_id"])

    def test_shared_model_admission_cannot_spend_the_compute_hold(self):
        self.reserve()
        self.store.add_spend("sail_model", 14.9)
        with self.assertRaises(ModelError):
            self.admit_model(0.01)
        self.assertEqual(self.store.spent(["sail_model"]), 14.9)

    def test_two_connections_cannot_reserve_the_same_room(self):
        self.store.add_spend("sail_model", 14.85)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        barrier = threading.Barrier(2)
        results = []
        def reserve(store, key):
            barrier.wait()
            try:
                compute.reserve(store, self.cfg, key, self.bound, kind="gate", now=self.clock())
                results.append("admitted")
            except compute.ComputeAdmissionError:
                results.append("refused")
        threads = [threading.Thread(target=reserve, args=args) for args in ((self.store, "a"), (other, "b"))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["admitted", "refused"])

    def test_failed_durable_admission_never_posts_and_rolls_back_the_hold(self):
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("synthetic transaction failure")):
            with self.assertRaises(RuntimeError): self.pool._start_box("gym")
        self.assertEqual(self.sail.forks, [])
        self.assertEqual(compute.remaining(self.store, now=self.clock()), 0)

    def test_restart_keeps_the_committed_room(self):
        self.reserve()
        reopened = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(reopened.close)
        self.assertEqual(compute.remaining(reopened, now=self.clock()), self.bound.usd)

    def test_estimated_booking_consumes_the_hold_without_double_counting(self):
        box = self.box()
        self.clock.advance(90)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]) + compute.remaining(self.store, now=self.clock()), self.bound.usd)

    def test_charge_replay_matches_incremental_booking_across_rounding_steps_and_restart(self):
        box = self.box()
        # Compensated SQLite SUM gives .01; the actual incremental booking gives the
        # adjacent float. Both represent this journal, which must remain runnable.
        for usd in (0.001, 0.008, 0.001):
            with self.store.atomic():
                self.store.add_spend("gym_box", usd, detail={"box": box.id})
                compute.book(self.store, box.id, usd)
        booked = self.store.get("compute_holds")["synthetic"]["booked_usd"]
        self.assertEqual(booked, 0.010000000000000002)
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd - booked)
        self.assertTrue(compute.runnable(self.store, box.id, now=self.clock(), seconds=1))
        reopened = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(reopened.close)
        self.assertEqual(compute.remaining(reopened, now=self.clock()), self.bound.usd - booked)

    def test_charge_replay_rejects_bad_rows_even_when_sql_aggregation_masks_them(self):
        box = self.box()
        for costs in ((0.01, -0.01), ("unpriced",), (math.inf,), (-math.inf,), ("NaN",)):
            with self.subTest(costs=costs):
                self.store._exec("DELETE FROM spend")
                for usd in costs:
                    self.store._exec("INSERT INTO spend(at,epoch,kind,usd,detail) VALUES(?,?,?,?,?)",
                                     (self.store.now(), self.clock(), "gym_box", usd,
                                      '{"box":"sb_compute"}'))
                self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
                self.assertFalse(compute.runnable(self.store, box.id, now=self.clock(), seconds=1))
                with self.assertRaises(ModelError): self.admit_model(0)

    def test_charge_replay_rejects_erasure_and_substantive_or_one_ulp_changes(self):
        box = self.box()
        with self.store.atomic():
            self.store.add_spend("gym_box", 0.01, detail={"box": box.id})
            compute.book(self.store, box.id, 0.01)
        for cost in (0, 0.009, math.nextafter(0.01, math.inf)):
            with self.subTest(cost=cost):
                self.store._exec("UPDATE spend SET usd=?", (cost,))
                self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
                self.assertFalse(compute.runnable(self.store, box.id, now=self.clock(), seconds=1))
        self.store._exec("DELETE FROM spend")
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_lost_create_keeps_its_entire_obligation(self):
        self.sail.from_checkpoint = mock.Mock(side_effect=TimeoutError("lost response"))
        self.pool._start_box("gym")
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd)
        self.assertIsNone(next(iter(self.store.get("compute_holds").values()))["box_id"])

    def test_lost_termination_stays_tracked_and_accrues_request_latency(self):
        box = self.box()
        def lost(box_id):
            self.clock.advance(5)
            raise TimeoutError("lost response")
        self.sail.terminate = lost
        self.clock.advance(10)
        self.pool._retire_box(box, "synthetic")
        self.clock.advance(100)
        self.pool.manage()
        self.assertEqual((box.state, self.row()["state"]), ("stopping", "stopping"))
        self.assertIn(box.id, self.pool.boxes)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 115 * 0.20 / 3600)
        self.assertIsNone(self.row()["detail"]["cost_cursor"]["unresolved_billing_interval"]["usd"])

    def test_transitional_termination_is_not_confirmation(self):
        box = self.box()
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "terminating"}
        self.pool._retire_box(box, "synthetic")
        self.clock.advance(60)
        self.pool._settle_rows([{"sailbox_id": box.id, "status": "terminating"}], grace=0)
        self.assertEqual((box.state, self.row()["state"]), ("stopping", "stopping"))
        self.assertTrue(self.row()["detail"]["cost_cursor"]["awake"])
        self.assertFalse(self.row()["detail"]["cost_cursor"]["billing_stop_confirmed"])

    def test_terminal_observation_closes_runtime_but_retains_unpriced_commitment(self):
        box = self.box()
        self.sail.terminate = lambda box_id: {"status": "terminating"}
        self.pool._retire_box(box, "synthetic")
        self.clock.advance(60)
        self.pool._settle_rows([{"sailbox_id": box.id, "status": "terminated"}], grace=0)
        self.assertEqual((box.state, self.row()["state"]), ("terminated", "terminated"))
        self.assertFalse(self.row()["detail"]["cost_cursor"]["awake"])
        held = next(iter(self.store.get("compute_holds").values()))
        self.assertTrue(held["confirmed_stopped"])
        self.assertFalse(held["billing_reconciled"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)

    def test_missing_inventory_entry_does_not_confirm_termination(self):
        box = self.box()
        self.sail.terminate = lambda box_id: {"status": "terminating"}
        self.pool._retire_box(box, "synthetic")
        self.pool._settle_rows([], grace=0)
        self.assertEqual(self.row()["state"], "stopping")
        self.assertFalse(self.row()["detail"]["cost_cursor"]["billing_stop_confirmed"])

    def test_transitional_sleep_keeps_accruing_until_sleep_is_observed(self):
        box = self.box()
        self.sail.sleep = lambda box_id: {"sailbox_id": box_id, "status": "running"}
        self.pool._sleep(box)
        self.clock.advance(60)
        self.pool._settle_rows([{"sailbox_id": box.id, "status": "sleeping"}], grace=0)
        self.assertEqual(self.row()["state"], "asleep")
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 60 * 0.20 / 3600)

    def test_crossing_midnight_refuses_even_when_ttl_itself_fits(self):
        self.clock.t = math.floor(self.clock() / 86400) * 86400 + 86400 - 1810
        with self.assertRaisesRegex(compute.ComputeAdmissionError, "midnight"):
            self.reserve()

    def test_expired_unconfirmed_obligation_closes_new_day_model_admission(self):
        row = self.reserve()
        self.clock.t = row["must_stop_by"]
        self.assertTrue(math.isinf(compute.remaining(self.store, since=self.clock(), now=self.clock())))
        with self.assertRaises(ModelError): self.admit_model(0.001)
        guard = SailGuard(self.store, self.cfg, lambda: (500, 0), clock=self.clock, disk_free=lambda: 100 * 2**30)
        self.assertIn("budget_unreadable", guard.check()["causes"])

    def test_corrupt_or_lost_hold_state_never_becomes_free_room(self):
        self.reserve()
        self.store._exec("UPDATE kv SET value='{' WHERE key='compute_holds'")
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        with self.assertRaises(ModelError): self.admit_model(0.001)
        self.store._exec("DELETE FROM kv WHERE key='compute_holds'")
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_invalid_or_expired_bound_never_admits(self):
        for name, value in (("max_usd_hour", float("nan")), ("fixed_usd", -1), ("max_stop_delay_seconds", float("inf")),
                            ("max_creation_delay_seconds", True), ("max_lifetime_seconds", False), ("max_lifetime_seconds", 4294967296)):
            with self.subTest(name=name), self.assertRaises(compute.ComputeAdmissionError): replace(self.bound, **{name: value})
        with self.assertRaises(compute.ComputeAdmissionError):
            compute.reserve(self.store, self.cfg, "expired", replace(self.bound, valid_until=self.clock()), kind="gate", now=self.clock())

    def test_unadmitted_batch_runs_nothing_and_consumes_no_retry_or_trial(self):
        box = Box("sb_unreserved", "gym", self.image, "ready", driver=FakeDriver(self.sail, "sb_unreserved"), roots=("SPY",))
        queued = self.pool.submit(job())
        self.pool.run_batch(box, [queued])
        self.assertEqual(box.driver.calls, [])
        self.assertEqual((queued.attempts, queued.done.is_set(), self.pool.queued()), (0, False, 1))

    def test_empty_or_partial_ledger_cannot_erase_immutable_commitments(self):
        self.reserve("a")
        self.reserve("b")
        original = self.store.get("compute_holds")
        for replacement in ({}, {"a": original["a"]}):
            with self.subTest(keys=list(replacement)):
                self.store.put("compute_holds", replacement)
                self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
                with self.assertRaises(ModelError): self.admit_model(0)
        self.store.put("compute_holds", original)
        self.assertAlmostEqual(compute.remaining(self.store, now=self.clock()), 2 * self.bound.usd)

    def test_nested_bound_or_binding_forgery_is_not_equal_to_admitted_history(self):
        self.bound = replace(self.bound, max_creation_delay_seconds=1)
        box = self.box()
        original = self.store.get("compute_holds")
        mutations = []
        boolean_price = copy.deepcopy(original)
        boolean_price["synthetic"]["bound"]["fixed_usd"] = True
        mutations.append(boolean_price)
        boolean_delay = copy.deepcopy(original)
        boolean_delay["synthetic"]["bound"]["max_creation_delay_seconds"] = True
        mutations.append(boolean_delay)
        erased_binding = copy.deepcopy(original)
        erased_binding["synthetic"]["box_id"] = None
        mutations.append(erased_binding)
        fake_stop = copy.deepcopy(original)
        fake_stop["synthetic"]["confirmed_stopped"] = True
        mutations.append(fake_stop)
        for replacement in mutations:
            self.store.put("compute_holds", replacement)
            self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        self.store.put("compute_holds", original)
        self.assertTrue(compute.runnable(self.store, box.id, now=self.clock(), seconds=1))

    def test_lost_or_falsely_reconciled_legacy_ledger_stays_unknown(self):
        compute.mark_uncovered(self.store, "sb_old_a")
        compute.mark_uncovered(self.store, "sb_old_b")
        original = self.store.get("compute_unpriced_legacy")
        forged = copy.deepcopy(original)
        for row in forged.values(): row["billing_reconciled"] = True
        for replacement in ({}, {"sb_old_a": original["sb_old_a"]}, forged):
            self.store.put("compute_unpriced_legacy", replacement)
            self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
            with self.assertRaises(ModelError): self.admit_model(0)
        self.store._exec("DELETE FROM kv WHERE key='compute_unpriced_legacy'")
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        self.store.put("compute_unpriced_legacy", original)
        compute.confirm_stopped(self.store, "sb_old_a", now=self.clock())
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_asleep_and_historical_terminated_resources_need_billing_evidence(self):
        for state in ("asleep", "terminated"):
            with self.subTest(state=state):
                self.store.upsert_box("sb_legacy", kind="gym", version=self.image, state=state)
                self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
                with self.assertRaises(compute.ComputeAdmissionError): self.reserve()
                with self.assertRaises(ModelError): self.admit_model(0)

    def test_unsent_cancellation_releases_only_an_immutable_never_dispatched_request(self):
        self.reserve("unsent")
        compute.cancel_unsent(self.store, "unsent")
        self.assertEqual(compute.remaining(self.store, now=self.clock()), 0)
        self.reserve("lost")
        compute.mark_dispatched(self.store, "lost")
        with self.assertRaises(compute.ComputeAdmissionError): compute.cancel_unsent(self.store, "lost")
        with self.assertRaises(compute.ComputeAdmissionError): compute.mark_dispatched(self.store, "lost")
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd)
        rows = self.store.get("compute_holds")
        rows["lost"].update(confirmed_stopped=True, billing_reconciled=True, never_dispatched=True)
        self.store.put("compute_holds", rows)
        self.store.event("swarm.pool", None, {"action": "compute_canceled_unsent", "key": "lost", "provider_dispatched": False})
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_dispatch_lifetime_refreshes_after_lock_wait(self):
        self.reserve()
        self.clock.advance(17.5)
        self.assertEqual(compute.mark_dispatched(self.store, "synthetic"), self.bound.max_lifetime_seconds - 18)

    def test_failed_lifecycle_receipt_rolls_back_binding_and_stop_state(self):
        self.reserve()
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("synthetic receipt failure")):
            with self.assertRaises(RuntimeError): compute.attach(self.store, "synthetic", "sb_compute")
        self.assertIsNone(self.store.get("compute_holds")["synthetic"]["box_id"])
        compute.attach(self.store, "synthetic", "sb_compute")
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("synthetic receipt failure")):
            with self.assertRaises(RuntimeError): compute.confirm_stopped(self.store, "sb_compute", now=self.clock())
        self.assertFalse(self.store.get("compute_holds")["synthetic"]["confirmed_stopped"])
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd)

    def test_failed_dispatch_receipt_keeps_request_provably_unsent(self):
        self.reserve()
        with mock.patch.object(self.store, "event", side_effect=RuntimeError("synthetic receipt failure")):
            with self.assertRaises(RuntimeError): compute.mark_dispatched(self.store, "synthetic")
        compute.cancel_unsent(self.store, "synthetic")
        self.assertEqual(compute.remaining(self.store, now=self.clock()), 0)

    def test_single_box_cannot_consume_two_reservations_or_change_identity(self):
        self.reserve("a")
        self.reserve("b")
        compute.attach(self.store, "a", "sb_one")
        with self.assertRaises(compute.ComputeAdmissionError): compute.attach(self.store, "b", "sb_one")
        with self.assertRaises(compute.ComputeAdmissionError): compute.attach(self.store, "a", "sb_two")
        self.assertEqual(compute.remaining(self.store, now=self.clock()), 2 * self.bound.usd)

    def test_terminal_observation_after_deadline_does_not_clear_a_breached_bound(self):
        box = self.box()
        self.clock.advance(self.bound.seconds + 1)
        compute.confirm_stopped(self.store, box.id, now=self.clock())
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        rows = self.store.get("compute_holds")
        rows["synthetic"].pop("breached")
        self.store.put("compute_holds", rows)
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        with self.assertRaises(ModelError): self.admit_model(0)

    def test_repeated_terminal_observation_preserves_first_proof_and_billing_hold(self):
        box = self.box()
        self.clock.advance(10)
        compute.confirm_stopped(self.store, box.id, now=self.clock())
        original = self.store.get("compute_holds")["synthetic"]
        self.clock.advance(self.bound.seconds + 1)
        compute.confirm_stopped(self.store, box.id, now=self.clock())
        self.assertEqual(self.store.get("compute_holds")["synthetic"], original)
        self.assertFalse(original["billing_reconciled"])
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd)
        events = [row for row in compute._history(self.store) if row.get("action") == "compute_runtime_stopped"]
        self.assertEqual(len(events), 1)
        with self.assertRaises(compute.ComputeAdmissionError):
            compute.confirm_stopped(self.store, box.id, now=original["stopped_observed_at"] - 1)
        self.assertEqual(self.store.get("compute_holds")["synthetic"], original)

    def test_repeated_legacy_terminal_observation_remains_unknown_at_original_time(self):
        compute.mark_uncovered(self.store, "sb_old")
        self.clock.advance(10)
        compute.confirm_stopped(self.store, "sb_old", now=self.clock())
        original = self.store.get("compute_unpriced_legacy")["sb_old"]
        self.clock.advance(86400)
        compute.confirm_stopped(self.store, "sb_old", now=self.clock())
        self.assertEqual(self.store.get("compute_unpriced_legacy")["sb_old"], original)
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_zero_additional_model_retry_still_checks_unknown_compute_obligations(self):
        self.admit_model(0.02)
        compute.mark_uncovered(self.store, "sb_unknown")
        with self.assertRaises(ModelError): self.admit_model(0.02)
        self.assertAlmostEqual(self.store.spent(["sail_model"]), 0.02)

    def test_invalid_or_unrepresentable_clock_closes_every_paid_admission(self):
        guard = SailGuard(self.store, self.cfg, mock.Mock(return_value=(500, 0)), clock=self.clock,
                          disk_free=lambda: 100 * 2**30)
        for value in (True, "bad", math.nan, math.inf, -1, 10**1000, 1e20):
            with self.subTest(clock=str(value)[:40]):
                self.clock.t = value
                self.assertTrue(math.isinf(compute.remaining(self.store)))
                with self.assertRaises(compute.ComputeAdmissionError): self.reserve()
                with self.assertRaises(ModelError): self.admit_model(0)
                self.assertIn("budget_unreadable", guard.check()["causes"])
                self.assertFalse(guard.allows())
        guard.reader.assert_not_called()

    def test_invalid_provider_balance_brakes_without_overwriting_last_good_or_meter(self):
        reader = mock.Mock(return_value=(500, 0))
        guard = SailGuard(self.store, self.cfg, reader, clock=self.clock, disk_free=lambda: 100 * 2**30)
        guard.check()
        self.assertTrue(guard.allows())
        last_good = dict(guard.last_good)
        metered_balance = self.store.get("metered_last_balance")
        for value in (math.nan, math.inf, -math.inf, True, False, -1, "bad", "500", 10**1000):
            with self.subTest(balance=str(value)[:40]):
                reader.return_value = (value, 0)
                self.clock.advance(1)
                result = guard.check()
                self.assertIn("balance_unreadable", result["causes"])
                self.assertIsNone(result["balance"])
                self.assertFalse(guard.allows())
                self.assertEqual(guard.last_good, last_good)
                self.assertEqual(self.store.get("metered_last_balance"), metered_balance)
        reader.return_value = (500, 0)
        guard.check()
        self.assertTrue(guard.allows())

    def test_invalid_provider_burn_stays_unknown_and_keeps_configured_house_floor(self):
        self.cfg["guard"]["measured_burn"] = True
        reader = mock.Mock()
        guard = SailGuard(self.store, self.cfg, reader, clock=self.clock, disk_free=lambda: 100 * 2**30)
        for value in (math.nan, math.inf, True, -1, "bad", 10**1000):
            reader.return_value = (500, value)
            result = guard.check()
            self.assertIsNone(result["burn_day"])
            self.assertGreaterEqual(result["house_day"], self.cfg["guard"]["house_burn_usd_day"])
            self.assertTrue(guard.allows())

    def test_malformed_contract_and_duplicate_history_fail_closed(self):
        for gym in (None, [], "bad"):
            cfg = {**self.cfg, "gym": gym}
            with self.assertRaises(compute.ComputeAdmissionError): compute.bound_for(cfg, self.image)
        for value in (True, 10**1000, 1e308):
            with self.assertRaises(compute.ComputeAdmissionError): replace(self.bound, max_usd_hour=value)
        original = self.reserve()
        self.store.event("swarm.pool", None, {"action": "compute_reserved", "key": "synthetic", **original})
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_negative_or_nonfinite_booking_cannot_refund_a_commitment(self):
        box = self.box()
        for usd in (-1, math.nan, math.inf, True, 10**1000):
            with self.assertRaises(compute.ComputeAdmissionError): compute.book(self.store, box.id, usd)
        self.assertEqual(compute.remaining(self.store, now=self.clock()), self.bound.usd)


if __name__ == "__main__": unittest.main()

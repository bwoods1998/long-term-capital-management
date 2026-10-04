"""Offline resource-cost intervals: confirmed sleep latency, UTC epochs, restart cursors, and atomic failures."""

from __future__ import annotations

import datetime as dt
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from league.swarm.pool import Box, GymPool, PoolError
from league.swarm import compute
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail, compute_budget_fixture
from league.tests.test_swarm_pool import job, settings


RATE = 0.20 / 3600.0


class BoxAccounting(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.directory.name), clock=self.clock)
        self.addCleanup(self.store.close)
        compute_budget_fixture(self.store.root, self.clock())
        self.sail = FakeSail()
        self.pool = self.make_pool()

    def make_pool(self, **gym):
        return GymPool(self.store, self.sail, settings(**gym), clock=self.clock, threaded=False,
                       driver_factory=lambda client, box: FakeDriver(client, box))

    def box(self, *, state="ready", booked_at=None):
        began = self.clock() if booked_at is None else booked_at
        compute_budget_fixture(self.store.root, self.clock())
        box = Box("sb_cost", "gym", str(self.pool.image("gym")), state,
                  driver=FakeDriver(self.sail, "sb_cost"), roots=("SPY",), booked_at=began)
        self.pool.boxes[box.id] = box
        if self.clock() % 86400 + 3600 <= 86400:
            bound = compute.bound_for(self.pool.settings, box.version)
            key = f"accounting-{box.id}-{len(self.store.get('compute_holds') or {})}"
            compute.reserve(self.store, self.pool.settings, key, bound, kind="gym", now=self.clock())
            compute.attach(self.store, key, box.id)
        self.store.upsert_box(box.id, kind=box.kind, version=box.version, state=state,
                              detail={"name": "cost-test", "roots": ["SPY"],
                                      "cost_cursor": {"booked_at": began, "awake": state != "asleep", "estimate": True}})
        return box

    def row(self):
        return self.store.boxes(live=False)[0]

    def cursor(self):
        return self.row()["detail"]["cost_cursor"]

    def test_sleep_books_request_latency_then_stops_accruing(self):
        box = self.box()
        self.clock.advance(20)

        def slow_sleep(box_id):
            self.clock.advance(30)
            return {"sailbox_id": box_id, "status": "sleeping"}

        self.sail.sleep = slow_sleep
        self.pool._sleep(box)
        self.assertEqual((box.state, self.row()["state"], self.cursor()["awake"]), ("asleep", "asleep", False))
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 50 * RATE)
        self.clock.advance(3600)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 50 * RATE)

    def test_accepted_sleep_durably_marks_unconfirmed_billing_interval_as_unknown(self):
        box = self.box()
        self.clock.advance(20)
        self.sail.sleep = lambda box_id: {"sailbox_id": box_id, "status": "running"}
        self.pool._sleep(box)
        cursor = self.cursor()
        self.assertFalse(cursor["billing_stop_confirmed"])
        self.assertEqual(cursor["stop_accepted_at"], self.clock())
        self.assertEqual((box.state, cursor["awake"]), ("sleeping", True))
        self.assertEqual(cursor["unresolved_billing_interval"]["start"], self.clock())
        self.assertIsNone(cursor["unresolved_billing_interval"]["end"])
        self.assertIsNone(cursor["unresolved_billing_interval"]["usd"])
        accepted = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "sleep_accepted"]
        self.assertEqual(len(accepted), 1)
        self.assertFalse(accepted[0]["billing_stop_confirmed"])
        self.clock.advance(100)
        self.pool._accrue(box)
        self.assertEqual(self.cursor()["unresolved_billing_interval"], cursor["unresolved_billing_interval"],
                         "later estimates must not erase the unresolved vendor interval")

    def test_uncertain_sleep_keeps_awake_time_and_books_failed_request_latency(self):
        box = self.box()
        self.clock.advance(20)

        def lost_response(box_id):
            self.clock.advance(30)
            raise TimeoutError("response lost")

        self.sail.sleep = lost_response
        self.pool._sleep(box)
        self.assertEqual((box.state, self.row()["state"], self.cursor()["awake"]), ("sleeping", "sleeping", True))
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 50 * RATE)
        self.clock.advance(10)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 60 * RATE)

    def test_repeated_uncertain_stop_preserves_the_original_unresolved_interval(self):
        box = self.box()
        self.clock.advance(20)
        requested = self.clock()
        self.sail.terminate = mock.Mock(side_effect=TimeoutError("response lost"))
        self.pool._retire_box(box, "synthetic")
        self.clock.advance(40)
        self.pool._retire_box(box, "synthetic retry")
        self.assertEqual(self.cursor()["unresolved_billing_interval"]["start"], requested)
        self.assertEqual(self.cursor()["stop_requested_at"], self.clock())
        self.assertFalse(self.cursor()["runtime_stop_confirmed"])
        self.assertTrue(self.cursor()["awake"])
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 60 * RATE)

    def test_confirmed_runtime_stop_retains_unpriced_vendor_liability(self):
        box = self.box()
        self.clock.advance(20)
        self.assertTrue(self.pool._sleep(box))
        self.assertTrue(self.cursor()["runtime_stop_confirmed"])
        self.assertFalse(self.cursor()["billing_stop_confirmed"])
        self.assertFalse(self.cursor()["vendor_bill_reconciled"])
        self.assertIsNone(self.cursor()["unresolved_billing_interval"]["usd"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)

    def test_delayed_booking_splits_cost_at_utc_midnight(self):
        midnight = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc).timestamp()
        self.clock.t = midnight - 10
        box = self.box()
        self.clock.advance(20)
        self.pool._accrue(box, jobs=3)
        rows = self.store._all("SELECT epoch, at, usd, detail FROM spend ORDER BY epoch")
        self.assertEqual([r["epoch"] for r in rows], [midnight - 10, midnight])
        self.assertEqual([r["at"][:10] for r in rows], ["2026-10-03", "2026-10-04"])
        self.assertAlmostEqual(self.store.spent(["gym_box"], since=midnight), 10 * RATE)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 20 * RATE)
        import json
        details = [json.loads(r["detail"]) for r in rows]
        self.assertEqual([r["seconds"] for r in details], [10, 10])
        self.assertEqual([r["jobs"] for r in details], [3, 0])
        self.assertTrue(all(r["estimate"] and r["usd_hour"] == 0.20 for r in details))

    def test_epoch_zero_is_a_valid_start_cursor(self):
        self.clock.t = 0
        box = self.box()
        self.clock.advance(40)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 40 * RATE)

    def test_restart_continues_from_last_atomic_awake_cursor(self):
        box = self.box()
        self.clock.advance(100)
        self.pool._accrue(box)
        self.clock.advance(200)
        restarted = self.make_pool()
        self.assertEqual(restarted.adopt(), 1)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 300 * RATE)
        self.assertEqual(restarted.boxes[box.id].booked_at, self.clock())
        self.assertEqual(self.cursor()["booked_at"], self.clock())
        self.assertEqual(self.row()["detail"]["roots"], ["SPY"])
        self.assertEqual(self.row()["detail"]["name"], "cost-test")
        self.assertFalse(any(e["payload"].get("action") == "accounting_gap" for e in self.store.events_after(0)))

    def test_restart_does_not_bill_known_sleeping_interval(self):
        box = self.box(state="asleep")
        self.clock.advance(3600)
        restarted = self.make_pool()
        self.assertEqual(restarted.adopt(), 1)
        self.assertEqual(restarted.boxes[box.id].state, "asleep")
        self.assertEqual(self.store.spent(["gym_box"]), 0)
        self.assertFalse(self.cursor()["awake"])

    def test_legacy_awake_row_records_unknown_gap_without_inventing_cost(self):
        self.store.upsert_box("sb_legacy", kind="gym", version=str(self.pool.image("gym")), state="ready",
                              detail={"roots": ["SPY"]})
        self.clock.advance(3600)
        self.assertEqual(self.pool.adopt(), 1)
        self.assertEqual(self.store.spent(["gym_box"]), 0)
        gaps = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "accounting_gap"]
        self.assertEqual(len(gaps), 1)
        self.assertIsNone(gaps[0]["usd"])
        self.assertEqual(gaps[0]["reason"], "no durable awake-cost cursor")
        self.clock.advance(10)
        self.pool._accrue(self.pool.boxes["sb_legacy"])
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 10 * RATE)

    def test_malformed_durable_cursor_reports_unknown_and_starts_observation_now(self):
        invalid = [None, -1, float("nan"), float("inf"), True, "123"]
        for value in invalid:
            with self.subTest(cursor=value):
                self.store.upsert_box("sb_bad", kind="gym", version=str(self.pool.image("gym")), state="ready",
                                      detail={"cost_cursor": {"booked_at": value, "awake": True}})
                self.assertEqual(self.make_pool().adopt(), 1)
                self.assertEqual(self.store.spent(["gym_box"]), 0)
                self.assertEqual(self.cursor()["booked_at"], self.clock())
        gaps = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "accounting_gap"]
        self.assertEqual(len(gaps), len(invalid))
        self.assertTrue(all(g["usd"] is None and g["reason"] == "invalid durable awake-cost cursor" for g in gaps))

    def test_database_failure_rolls_back_spend_and_both_cursors_then_retry_books_once(self):
        box = self.box()
        began = box.booked_at
        self.clock.advance(25)
        real_exec = self.store._exec

        def fail_cursor(sql, params=()):
            if sql.startswith("UPDATE boxes SET detail"):
                raise RuntimeError("disk failure")
            return real_exec(sql, params)

        with mock.patch.object(self.store, "_exec", side_effect=fail_cursor):
            with self.assertRaisesRegex(RuntimeError, "disk failure"):
                self.pool._accrue(box)
        self.assertEqual(self.store.spent(["gym_box"]), 0)
        self.assertEqual((box.booked_at, self.cursor()["booked_at"]), (began, began))
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 25 * RATE)

    def test_second_day_failure_rolls_back_first_day_too(self):
        midnight = dt.datetime(2026, 10, 4, tzinfo=dt.timezone.utc).timestamp()
        self.clock.t = midnight - 10
        box = self.box()
        self.clock.advance(20)
        real_add = self.store.add_spend
        calls = []

        def fail_second(*args, **kwargs):
            calls.append(kwargs["at"])
            if len(calls) == 2:
                raise RuntimeError("second day unavailable")
            return real_add(*args, **kwargs)

        with mock.patch.object(self.store, "add_spend", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second day unavailable"):
                self.pool._accrue(box)
        self.assertEqual(self.store.spent(["gym_box"]), 0)
        self.assertEqual((box.booked_at, self.cursor()["booked_at"]), (midnight - 10, midnight - 10))
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 20 * RATE)

    def test_clock_rollback_preserves_cursor_and_never_rebooks_old_time(self):
        box = self.box()
        began = box.booked_at
        self.clock.advance(-10)
        self.pool._accrue(box)
        self.assertEqual((box.booked_at, self.cursor()["booked_at"]), (began, began))
        self.assertEqual(self.store.spent(["gym_box"]), 0)
        self.clock.advance(20)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 10 * RATE)

    def test_bad_rate_cannot_reduce_spend_or_advance_cursor(self):
        box = self.box()
        began = box.booked_at
        self.clock.advance(25)
        for rate in [-0.20, 0, float("nan"), float("inf"), None, True]:
            with self.subTest(rate=rate):
                self.pool.settings["gym"]["box_usd_hour"] = rate
                with self.assertRaisesRegex(PoolError, "cost is unknown"):
                    self.pool._accrue(box)
                self.assertEqual(self.store.spent(["gym_box"]), 0)
                self.assertEqual((box.booked_at, self.cursor()["booked_at"]), (began, began))

    def test_resume_persists_awake_start_before_request_and_books_latency(self):
        box = self.box(state="asleep")
        self.clock.advance(100)
        resuming = self.clock()

        def slow_resume(box_id):
            self.assertEqual(self.cursor()["booked_at"], resuming)
            self.assertTrue(self.cursor()["awake"])
            self.clock.advance(30)
            return {}

        self.sail.resume = slow_resume
        self.pool.run_batch(box, [job()])
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 30 * RATE)
        self.assertEqual(box.state, "ready")

    def test_restart_after_resume_crash_preserves_its_continuous_awake_estimate(self):
        self.box(state="asleep")
        self.clock.advance(100)
        began = self.clock()

        def lost_process(box_id):
            self.clock.advance(20)
            raise KeyboardInterrupt("process ended before resume response")

        self.sail.resume = lost_process
        with self.assertRaises(KeyboardInterrupt):
            self.pool.run_batch(self.pool.boxes["sb_cost"], [job()])
        self.assertEqual((self.cursor()["booked_at"], self.cursor()["awake"]), (began, True))
        self.clock.advance(40)
        restarted = self.make_pool(book_seconds=10)
        self.assertEqual(restarted.adopt(), 1)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 60 * RATE)
        self.clock.advance(20)
        restarted.manage()
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 80 * RATE)
        self.sail.resume = lambda box_id: {}
        self.clock.advance(10)
        restarted.run_batch(restarted.boxes["sb_cost"], [job()])
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 90 * RATE,
                               msg="a pending resume cursor must not reset to zero at its retry")

    def test_concurrent_booking_commits_one_interval(self):
        box = self.box()
        self.clock.advance(25)
        failures = []

        def book():
            try:
                self.pool._accrue(box)
            except Exception as exc:
                failures.append(exc)

        threads = [threading.Thread(target=book) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 25 * RATE)

    def test_ready_publication_cannot_overwrite_a_concurrent_newer_cursor(self):
        real_upsert = self.store.upsert_box
        attempted = threading.Event()
        finished = threading.Event()
        threads, failures = [], []

        def interleaved_upsert(box_id, **kwargs):
            if kwargs["state"] == "ready":
                self.clock.advance(20)

                def book():
                    attempted.set()
                    try:
                        self.pool._accrue(self.pool.boxes[box_id])
                    except BaseException as exc:
                        failures.append(exc)
                    finally:
                        finished.set()

                worker = threading.Thread(target=book)
                threads.append(worker)
                worker.start()
                self.assertTrue(attempted.wait(2))
                if not self.pool._lock._is_owned():
                    # Reproduce the old interleaving deterministically: book t+20 before a stale t is published.
                    self.assertTrue(finished.wait(2))
                else:
                    self.assertFalse(finished.is_set(), "booking waits until the protected ready publication commits")
            return real_upsert(box_id, **kwargs)

        with mock.patch.object(self.store, "upsert_box", side_effect=interleaved_upsert):
            self.pool._start_box("gym")
        for worker in threads:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.cursor()["booked_at"], self.clock())
        self.clock.advance(10)
        self.assertEqual(self.make_pool().adopt(), 1)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 30 * RATE,
                               msg="startup and restart must book 30 elapsed seconds, not the old race's 50")

    def test_sleep_during_setup_stays_asleep_until_next_admitted_batch_resumes(self):
        clock, pool = self.clock, self.pool

        class SleptDuringSetup(FakeDriver):
            def ensure_code(inner):
                clock.advance(10)
                self.assertEqual(pool.boxes[inner.box].state, "starting")
                self.assertEqual(pool.scale_to_zero("synthetic setup brake"), 1)
                return super().ensure_code()

            def run(inner, *args, **kwargs):
                doc = super().run(*args, **kwargs)
                clock.advance(20)
                return doc

        self.pool.driver_factory = lambda client, box: SleptDuringSetup(client, box)
        self.pool._start_box("gym")
        box = next(iter(self.pool.boxes.values()))
        self.assertEqual((box.state, self.row()["state"], self.cursor()["awake"]), ("asleep", "asleep", False))
        self.assertIs(box.cost_awake, False)
        initialized = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "box_ready"]
        self.assertEqual(initialized[0]["state"], "asleep")
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 10 * RATE)
        clock.advance(20)
        self.pool._accrue(box)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 10 * RATE)

        real_resume = self.sail.resume

        def slow_resume(box_id):
            self.assertTrue(self.cursor()["awake"], "wake accounting starts before the admitted resume request")
            clock.advance(30)
            return real_resume(box_id)

        self.sail.resume = slow_resume
        admitted = self.pool.submit(job())
        clock.advance(9)
        self.assertTrue(self.pool.allowed("gym"))
        batch = self.pool._take(box)
        self.assertEqual(batch, [admitted])
        self.pool.run_batch(box, batch)
        self.assertEqual(self.sail.resumed, [box.id])
        self.assertEqual((box.state, self.row()["state"], self.cursor()["awake"]), ("ready", "ready", True))
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 60 * RATE,
                               msg="ten setup seconds plus thirty resume and twenty batch seconds are estimated")


if __name__ == "__main__":
    unittest.main()

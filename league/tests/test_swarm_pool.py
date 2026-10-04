"""The Gym pool (league/swarm/pool.py): sealed forks of the Gym image, day-major batches, sleep, version change,
the guard's brake, and failures that never kill the pool. A fake Sail and a fake Gym driver."""

from __future__ import annotations

import copy
from dataclasses import asdict
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import pool as pool_mod
from league.swarm import compute
from league.swarm import settings as S
from league.swarm.pool import Box, GymJob, GymPool, PoolError, cleanup_stopped
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail, compute_budget_fixture


def settings(**gym):
    out = copy.deepcopy(S.DEFAULTS)
    out["budget"] = {"source": "synthetic", "sail_usd_day": 15.0, "claude_usd_day": 10.0}
    out["gym"].update({"enabled": True, "image_checkpoint": "sbcp_11111111-aaaa", "gate_checkpoint": "sbcp_22222222-bbbb",
                       "batch_wait_seconds": 8, "batch_programs": 3, **gym})
    out["gym"]["compute_bounds"] = {
        image: asdict(compute.ComputeBound(image, 0.20, 0.0, 3600, 0, 0, 4102444800.0,
                                          "synthetic synchronous fake provider contract"))
        for image in (out["gym"]["image_checkpoint"], out["gym"]["gate_checkpoint"]) if image}
    return out


def job(family="f", window="train", stress=1.0, roots=("SPY",), priority=0.0, gate=None):
    return GymJob(family=family, version=1, code="NEEDS = {}", params={}, window=window, roots=tuple(roots), stress=stress,
                  priority=priority, gate=gate)


class PoolCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        compute_budget_fixture(self.store.root, self.clock())
        self.sail = FakeSail()
        self.calls: list = []
        self.allowed = {"gym": True, "gate": True}
        self.failure = None

    def pool(self, **gym):
        p = GymPool(self.store, self.sail, settings(**gym), clock=self.clock, threaded=False, allowed=lambda k: self.allowed[k],
                    driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls, fail=lambda: self.failure))
        return p

    def ready_box(self, pool, kind="gym", image=None):
        image = image or pool.image(kind)
        # Separate pools can share this durable store; their physical IDs must not alias an earlier hold.
        ordinal = len(self.store.get("compute_holds") or {}) + 1
        box = Box(f"sb_{ordinal:08d}-ffff-ffff-ffff-ffffffffffff", kind, str(image), "ready",
                  driver=FakeDriver(self.sail, "x", calls=self.calls, fail=lambda: self.failure), roots=("SPY", "QQQ", "IWM", "XSP", "SPXW"),
                  last_used=self.clock())
        pool.boxes[box.id] = box
        bound = compute.ComputeBound(str(image), 0.20, 0.0, 3600, 0, 0, 4102444800.0,
                                     "synthetic synchronous fake provider contract")
        key = f"fixture-{box.id}-{len(self.store.get('compute_holds') or {})}"
        compute.reserve(self.store, pool.settings, key, bound, kind=kind, now=self.clock())
        compute.attach(self.store, key, box.id)
        self.store.upsert_box(box.id, kind=kind, version=str(image), state="ready",
                              detail={"cost_cursor": {"awake": True, "booked_at": self.clock(), "estimate": True}})
        box.booked_at = self.clock()
        return box


class Batches(PoolCase):
    def test_a_short_batch_waits_for_company_then_goes(self):
        pool = self.pool()
        box = self.ready_box(pool)
        pool.submit(job("a"))
        self.assertEqual(pool._take(box), [])
        self.clock.advance(9)
        self.assertEqual([j.family for j in pool._take(box)], ["a"])

    def test_a_full_batch_goes_at_once_highest_priority_first_same_settings_only(self):
        pool = self.pool()
        box = self.ready_box(pool)
        for name, pr in (("low", 0.1), ("high", 0.9), ("mid", 0.5), ("other", 0.95)):
            pool.submit(job(name, priority=pr, stress=1.5 if name == "other" else 1.0))
        pool.submit(job("more", priority=0.2))
        self.assertEqual(pool._take(box), [], "the head (another stress) is alone and waits for company")
        self.clock.advance(9)
        self.assertEqual([j.family for j in pool._take(box)], ["other"])
        self.assertEqual([j.family for j in pool._take(box)], ["high", "mid", "more"], "a full batch goes at once")
        self.assertEqual([j.family for j in pool._take(box)], ["low"])

    def test_a_batch_runs_day_major_on_one_box_and_delivers_each_result(self):
        pool = self.pool()
        box = self.ready_box(pool)
        jobs = [pool.submit(job(n, roots=r)) for n, r in (("a", ("SPY",)), ("b", ("QQQ",)), ("c", ("SPY",)))]
        pool.run_batch(box, pool._take(box))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["roots"], ["QQQ", "SPY"])
        for j in jobs:
            self.assertTrue(j.done.is_set())
            self.assertEqual(pool.wait(j, 0)["status"], "ok")
        self.assertEqual(pool.stats["jobs"], 3)
        self.assertGreater(self.store.spent(["gym_box"]), -1)  # booked (zero seconds on a frozen clock)

    def test_each_result_names_the_gym_image_and_engine_bundle_it_ran_on(self):
        pool = self.pool()
        box = self.ready_box(pool)
        box.driver.version = "engine-synthetic-v1"
        [j] = [pool.submit(job("a"))]
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual(j.result["gym_image"], box.version)
        self.assertEqual(j.result["gym_bundle"], box.driver.version)
        self.assertEqual(pool.bundle(), box.driver.version)

    def test_a_root_the_box_lacks_fails_its_job_at_once(self):
        pool = self.pool()
        box = self.ready_box(pool)
        box.roots = ("SPY",)
        bad = pool.submit(job("x", roots=("TSLA",)))
        good = pool.submit(job("y"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError) as caught:
            pool.wait(bad, 0)
        self.assertIn("no train data for TSLA", str(caught.exception))
        self.assertEqual(pool.wait(good, 0)["status"], "ok")

    def test_a_failed_batch_is_retried_once_then_its_jobs_fail_and_the_box_survives(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.failure = RuntimeError("exec 503")
        j = pool.submit(job("a"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertFalse(j.done.is_set())
        self.assertEqual(pool.queued(), 1)
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError):
            pool.wait(j, 0)
        self.assertEqual(box.state, "ready")

    def test_missing_data_fails_the_batch_without_a_retry(self):
        class GymDataMissing(Exception):
            pass

        pool = self.pool()
        box = self.ready_box(pool)
        self.failure = GymDataMissing("no validation days for SPY")
        j = pool.submit(job("a", window="validation"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError) as caught:
            pool.wait(j, 0)
        self.assertIn("missing data", str(caught.exception))

    def test_a_wait_that_times_out_withdraws_a_queued_job_and_records_a_running_one_when_it_lands(self):
        pool = self.pool()
        box = self.ready_box(pool)
        queued = pool.submit(job("q"))
        with self.assertRaises(PoolError):
            pool.wait(queued, 0.01, late=lambda r: self.fail("never ran"))
        self.assertEqual(pool.queued(), 0, "withdrawn: nothing ran")
        running = pool.submit(job("r"))
        self.clock.advance(9)
        batch = pool._take(box)
        landed = []
        with self.assertRaises(PoolError):
            pool.wait(running, 0.01, late=landed.append)
        pool.run_batch(box, batch)
        self.assertEqual([r["status"] for r in landed], ["ok"], "the evaluation happened: it is recorded")

    def test_gate_jobs_go_only_to_gate_boxes_and_never_wait_for_company(self):
        pool = self.pool()
        gym = self.ready_box(pool, "gym")
        gate = self.ready_box(pool, "gate")
        j = pool.submit(job("a", window="holdout", gate="holdout look a v1"))
        self.assertEqual(pool._take(gym), [])
        batch = pool._take(gate)
        self.assertEqual(batch, [j])
        pool.run_batch(gate, batch)
        self.assertEqual(self.calls[-1]["gate"], "holdout look a v1")


class Boxes(PoolCase):
    def test_demand_forks_the_start_boxes_from_the_gym_image_and_more_while_the_queue_is_long(self):
        pool = self.pool(start_boxes=4, max_boxes=8, batch_programs=2)
        for i in range(3):
            pool.submit(job(f"f{i}"))
        out = pool.manage()
        self.assertEqual(out["started"], 4)
        self.assertEqual([c for c, _ in self.sail.forks], ["sbcp_11111111-aaaa"] * 4)
        self.assertEqual(sum(1 for b in pool.boxes.values() if b.state == "ready"), 4)
        for i in range(20):
            pool.submit(job(f"g{i}"))
        pool.manage()
        self.assertEqual(len(self.sail.forks), 8, "up to max_boxes while the queue is long")
        pool.manage()
        self.assertEqual(len(self.sail.forks), 8)

    def test_no_work_no_boxes_and_idle_boxes_sleep(self):
        pool = self.pool(idle_sleep_seconds=600)
        pool.manage()
        self.assertEqual(self.sail.forks, [])
        box = self.ready_box(pool)
        self.clock.advance(601)
        pool.manage()
        self.assertEqual((box.state, self.sail.slept), ("asleep", [box.id]))

    def test_a_sleeping_box_counts_and_is_resumed_for_its_next_batch(self):
        pool = self.pool(start_boxes=1)
        box = self.ready_box(pool)
        box.state = "asleep"
        pool.submit(job("a"))
        pool.manage()
        self.assertEqual(self.sail.forks, [], "a sleeper is capacity: no fork")
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual(self.sail.resumed, [box.id])

    def test_a_box_of_an_old_image_is_terminated(self):
        pool = self.pool()
        box = self.ready_box(pool, image="sbcp_old")
        pool.manage()
        self.assertEqual((box.state, self.sail.terminated), ("terminated", [box.id]))

    def test_the_guards_brake_sleeps_boxes_and_stops_forks(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.allowed["gym"] = False
        pool.submit(job("a"))
        out = pool.manage()
        self.assertEqual((out["started"], box.state), (0, "asleep"))
        self.assertEqual(pool.scale_to_zero("brake"), 0)
        self.allowed["gym"] = True
        box.state = "ready"
        self.assertEqual(pool.scale_to_zero("brake"), 1)

    def test_a_failed_fork_backs_off_instead_of_forking_again(self):
        class Refusing(FakeSail):
            def from_checkpoint(self, checkpoint, *, name, timeout=900.0, max_lifetime_seconds=None):
                self.forks.append((checkpoint, None))
                raise RuntimeError("checkpoint not found")

        self.sail = Refusing()
        pool = self.pool(start_boxes=2)
        pool.submit(job("a"))
        pool.manage()
        self.assertEqual(len(self.sail.forks), 2)
        out = pool.manage()
        self.assertEqual(len(self.sail.forks), 2, "no storm")
        self.assertGreater(out["fork_backoff"], 0)
        self.clock.advance(3600)
        pool.manage()
        self.assertEqual(len(self.sail.forks), 2, "an expired unresolved create blocks another admission")

    def test_boxes_carry_the_swarms_own_name_prefix_and_its_stores_token(self):
        pool = self.pool(start_boxes=1)
        pool.submit(job("a"))
        pool.manage()
        token = self.store.get("pool_token")
        self.assertRegex(token, r"^[0-9a-f]{6}$")
        self.assertTrue(all(n.startswith(f"ltcm-swarm-{token}-gym-") for n in self.sail.names.values()), self.sail.names)
        self.assertEqual(self.pool().token, token, "the token lives with the store")

    def test_strays_named_like_ours_are_terminated_and_other_boxes_left_alone(self):
        pool = self.pool()
        old = self.clock() - 3600
        self.sail.extra = [{"sailbox_id": "sb_deadbeef", "name": f"ltcm-swarm-{pool.token}-gym-1-9", "status": "running", "created_at": old},
                           {"sailbox_id": "sb_trial", "name": "ltcm-swarm-0a0a0a-gym-1-9", "status": "running", "created_at": old},
                           {"sailbox_id": "sb_young", "name": f"ltcm-swarm-{pool.token}-gym-2-9", "status": "running",
                            "created_at": self.clock() - 30},
                           {"sailbox_id": "sb_w1", "name": "ltcm-gym-image-v1", "status": "running"},
                           {"sailbox_id": "sb_house", "name": "ltcm-floor", "status": "running"}]
        pool.adopt()
        self.assertEqual(self.sail.terminated, ["sb_deadbeef"], "another store's boxes and a box made minutes ago are left alone")

    def test_boxes_named_before_the_token_are_adopted_when_known_and_ended_when_stray(self):
        """Stage 1 named its boxes `ltcm-swarm-<kind>-<epoch>-<n>` (no token): the release after it takes them over."""
        old = int(self.clock()) - 3600
        self.store.upsert_box("sb_known", kind="gym", version="sbcp_11111111-aaaa", state="asleep",
                              detail={"name": f"ltcm-swarm-gym-{old}-1"})
        self.sail.extra = [{"sailbox_id": "sb_known", "name": f"ltcm-swarm-gym-{old}-1", "status": "sleeping"},
                           {"sailbox_id": "sb_deadbee0", "name": f"ltcm-swarm-gym-{old}-2", "status": "running"},
                           {"sailbox_id": "sb_deadbee1", "name": f"ltcm-swarm-gate-{old}-3", "status": "running"},
                           {"sailbox_id": "sb_new", "name": f"ltcm-swarm-gym-{int(self.clock()) - 60}-4", "status": "running"},
                           {"sailbox_id": "sb_other", "name": f"ltcm-swarm-0a0a0a-gym-{old}-1", "status": "running"},
                           {"sailbox_id": "sb_w1", "name": "ltcm-gym-image-v1", "status": "running"}]
        pool = self.pool()
        self.assertEqual(pool.adopt(), 1)
        self.assertEqual(pool.boxes["sb_known"].state, "asleep", "a box the store knows is adopted, whatever its name")
        self.assertEqual(sorted(self.sail.terminated), ["sb_deadbee0", "sb_deadbee1"], "untokened strays older than the grace end")

    def test_stopping_sleeps_busy_boxes_too_the_brake_does_not(self):
        pool = self.pool()
        box = self.ready_box(pool)
        box.state = "busy"
        self.assertEqual(pool.scale_to_zero("brake"), 0, "the guard's brake lets a running batch finish")
        self.assertEqual(pool.scale_to_zero("stopped", busy=True), 1, "a stopping process loses the batch anyway")
        self.assertEqual(self.sail.slept, [box.id])

    def test_the_cap_counts_the_stores_live_boxes_too(self):
        for i in range(6):
            cfg = settings()
            compute.reserve(self.store, cfg, f"fixture-row-{i}", compute.bound_for(cfg, "sbcp_11111111-aaaa"),
                            kind="gym", now=self.clock())
            compute.attach(self.store, f"fixture-row-{i}", f"sb_row{i}")
            self.store.upsert_box(f"sb_row{i}", kind="gym", version="sbcp_11111111-aaaa", state="ready", detail={})
        pool = self.pool(start_boxes=4, max_boxes=8, batch_programs=1)
        for i in range(20):
            pool.submit(job(f"f{i}"))
        pool.manage()
        self.assertEqual(len(self.sail.forks), 2, "eight boxes, six of them known only to the store")

    def test_a_box_that_fails_to_resume_is_failed_in_the_store_and_ended(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.store.upsert_box(box.id, kind="gym", version=box.version, state="asleep", detail={})
        box.state = "asleep"

        def refuse(box_id, **kw):
            raise RuntimeError("HTTP 409 not resumable")

        self.sail.resume = refuse
        pool.submit(job("a"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual(self.store.boxes(live=False)[0]["state"], "terminated", "Sail took the terminate call")
        self.assertEqual(self.sail.terminated, [box.id])
        self.assertEqual(len(pool.queue), 1, "its job goes back to the queue")
        self.assertIn("resume_failed", [e["payload"].get("action") for e in self.store.events_after(0) if e["kind"] == "swarm.pool"])

    def test_awake_idle_and_resume_time_is_booked_asleep_time_is_not(self):
        rate = 0.20 / 3600
        pool = self.pool(idle_sleep_seconds=600)
        box = self.ready_box(pool)
        box.booked_at = self.clock()
        self.clock.advance(400)
        pool.manage()
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 400 * rate, places=6)
        self.clock.advance(300)
        pool.manage()  # idle 700 s: asleep, its last 300 awake seconds booked
        self.assertEqual(box.state, "asleep")
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 700 * rate, places=6)
        self.clock.advance(100)
        pool.manage()
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 700 * rate, places=6, msg="asleep costs nothing")

        def slow_resume(box_id, **kw):
            self.clock.advance(30)
            return {}

        self.sail.resume = slow_resume
        pool.submit(job("a"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertAlmostEqual(self.store.spent(["gym_box"]), (700 + 30) * rate, places=6)

    def test_stop_waits_for_a_fork_in_flight_and_puts_its_box_to_sleep(self):
        import threading

        release = threading.Event()
        entered = threading.Event()
        real = self.sail.from_checkpoint

        def slow_post(checkpoint, *, name, timeout=900.0, max_lifetime_seconds=None):
            entered.set()
            release.wait(5)
            return real(checkpoint, name=name, max_lifetime_seconds=max_lifetime_seconds)

        self.sail.from_checkpoint = slow_post
        pool = GymPool(self.store, self.sail, settings(start_boxes=1), clock=self.clock, threaded=True,
                       driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls))
        pool.submit(job("a"))
        pool.manage()
        self.assertTrue(entered.wait(2), "this regression requires the provider request to be in flight")
        threading.Timer(0.2, release.set).start()
        pool.stop(join_seconds=5)
        self.assertFalse(any(t.is_alive() for t in pool.fork_threads), "no fork outlives the pool")
        self.assertEqual([b.state for b in pool.boxes.values()], ["asleep"])
        self.assertEqual(self.sail.slept, [self.sail.forks[0][1]])

    def test_a_fork_in_flight_is_never_taken_for_a_stray(self):
        sail = self.sail
        pool = self.pool(start_boxes=1)
        real = sail.from_checkpoint

        def slow_post(checkpoint, *, name, timeout=900.0, max_lifetime_seconds=None):
            row = real(checkpoint, name=name, max_lifetime_seconds=max_lifetime_seconds)  # created before its response
            pool.reconcile()  # the main thread's sweep, meanwhile
            return row

        sail.from_checkpoint = slow_post
        pool.submit(job("a"))
        pool.manage()
        self.assertEqual(sail.terminated, [], "a fork whose POST is in flight is ours")
        self.assertEqual(sum(1 for b in pool.boxes.values() if b.state == "ready"), 1)

    def test_an_unsealed_fork_is_terminated_and_never_used(self):
        self.sail.sealed = False
        pool = self.pool(start_boxes=1)
        pool.submit(job("a"))
        pool.manage()
        self.assertEqual(len(self.sail.terminated), 1)
        self.assertFalse([b for b in pool.boxes.values() if b.state == "ready"])
        events = [e["payload"].get("action") for e in self.store.events_after(0) if e["kind"] == "swarm.pool"]
        self.assertIn("unsealed", events)

    def test_forks_are_capped_per_hour(self):
        pool = self.pool(start_boxes=8, max_boxes=8, max_forks_hour=5)
        for i in range(20):
            pool.submit(job(f"f{i}"))
        pool.manage()
        self.assertEqual(len(self.sail.forks), 5)
        for b in list(pool.boxes.values()):
            pool._retire_box(b, "test")
        pool.manage()
        self.assertEqual(len(self.sail.forks), 5, "the hour's forks are spent")
        self.clock.advance(3601)
        pool.manage()
        self.assertGreater(len(self.sail.forks), 5)

    def test_startup_time_is_booked(self):
        class Slow(FakeDriver):
            def ensure_code(inner):
                self.clock.advance(120)
                return "x"

        pool = GymPool(self.store, self.sail, settings(start_boxes=1), clock=self.clock, threaded=False,
                       driver_factory=lambda client, box: Slow(client, box))
        pool.submit(job("a"))
        pool.manage()
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 120 * 0.20 / 3600, places=6)

    def test_repeated_startup_failures_make_the_gym_unavailable_and_say_so(self):
        class Broken(FakeDriver):
            def ensure_code(inner):
                raise RuntimeError("python not found at /opt/data-venv/bin/python")

        pool = GymPool(self.store, self.sail, settings(start_boxes=1), clock=self.clock, threaded=False,
                       driver_factory=lambda client, box: Broken(client, box))
        pool.submit(job("a"))
        for _ in range(3):
            pool.manage()
            self.clock.advance(3600)
        self.assertTrue(pool.unavailable("gym"))
        alerts = [e for e in self.store.events_after(0) if e["kind"] == "swarm.status" and e["payload"].get("action") == "gym_unavailable"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual([b for b in pool.boxes.values() if b.state == "failed"], [], "failed boxes are not kept")
        pool.driver_factory = lambda client, box: FakeDriver(client, box)  # the image is fixed
        pool.cancel_family("a")
        self.clock.advance(3600)
        pool.manage()
        self.assertFalse(pool.unavailable("gym"), "one probe fork after the backoff finds it back with no demand")

    def test_a_newer_train_job_supersedes_a_queued_one_of_the_same_family(self):
        pool = self.pool()
        old = pool.submit(job("a"))
        new = pool.submit(job("a"))
        pool.submit(job("b"))
        self.assertEqual(pool.queued(), 2)
        with self.assertRaises(PoolError):
            pool.wait(old, 0)
        self.assertFalse(new.done.is_set())

    def test_no_image_no_gym(self):
        pool = self.pool(image_checkpoint=None)
        pool.submit(job("a"))
        self.assertEqual(pool.manage()["started"], 0)

    def test_a_restart_adopts_its_boxes_and_terminates_stale_ones(self):
        pool = self.pool()
        self.store.upsert_box("sb_00000001-0000-0000-0000-000000000000", kind="gym", version="sbcp_11111111-aaaa", state="asleep",
                              detail={"roots": ["SPY"]})
        self.store.upsert_box("sb_00000002-0000-0000-0000-000000000000", kind="gym", version="sbcp_old", state="ready")
        self.assertEqual(pool.adopt(), 1)
        self.assertEqual(self.sail.terminated, ["sb_00000002-0000-0000-0000-000000000000"])
        self.assertEqual(pool.boxes["sb_00000001-0000-0000-0000-000000000000"].state, "asleep")

    def test_threaded_dispatch_end_to_end(self):
        pool = GymPool(self.store, self.sail, settings(start_boxes=1, batch_wait_seconds=0), clock=self.clock, threaded=True,
                       driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls))
        self.addCleanup(pool.stop)
        j = pool.submit(job("a"))
        pool.manage()
        self.assertEqual(pool.wait(j, 10)["status"], "ok")



class Rows(PoolCase):
    """THE ROWS (Oct 2, 2026: six `failed` rows sat in the pool table, their boxes long terminated on Sail)."""

    def state(self, box_id):
        return {r["id"]: r["state"] for r in self.store.boxes(live=False)}.get(box_id)

    def actions(self, name):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.pool" and e["payload"].get("action") == name]

    def refuse_terminate(self, *ids):
        real = self.sail.terminate

        def terminate(box_id):
            if box_id in ids:
                raise RuntimeError("HTTP 503")
            return real(box_id)

        self.sail.terminate = terminate

    def test_a_box_that_fails_to_start_is_terminated_in_the_store_once_sail_takes_the_call(self):
        class Broken(FakeDriver):
            def ensure_code(inner):
                raise RuntimeError("python not found")

        pool = GymPool(self.store, self.sail, settings(start_boxes=1), clock=self.clock, threaded=False,
                       driver_factory=lambda client, box: Broken(client, box))
        pool.submit(job("a"))
        pool.manage()
        box_id = self.sail.forks[0][1]
        self.assertEqual(self.sail.terminated, [box_id])
        self.assertEqual(self.state(box_id), "terminated")
        self.assertEqual(len(self.actions("box_failed")), 1, "the failure is still recorded")

    def test_a_refused_terminate_leaves_the_row_failed_until_sail_lists_the_box_gone(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.store.upsert_box(box.id, kind="gym", version=box.version, state="asleep", detail={})
        box.state = "asleep"
        self.sail.resume = lambda box_id, **kw: (_ for _ in ()).throw(RuntimeError("HTTP 409 not resumable"))
        self.refuse_terminate(box.id)
        pool.submit(job("a"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual(self.state(box.id), "stopping", "a failed request leaves termination unresolved")
        self.sail.extra = [{"sailbox_id": box.id, "name": "x", "status": "terminated"}]  # Sail ended it on its own
        pool.reconcile()
        self.assertEqual(self.state(box.id), "terminated")
        self.assertEqual([(a["box"], a["was"], a["sail"]) for a in self.actions("row_settled")], [(box.id, "stopping", "terminated")])

    def test_reconcile_settles_failed_rows_against_sails_list(self):
        for i in range(1, 6):
            self.store.upsert_box(f"sb_f{i}", kind="gym", version="sbcp_11111111-aaaa", state="failed", detail={})
        self.store.upsert_box("sb_ok", kind="gym", version="sbcp_11111111-aaaa", state="terminated", detail={})
        self.sail.extra = [{"sailbox_id": "sb_f2", "name": "n2", "status": "running"},      # still billing: ended
                           {"sailbox_id": "sb_f3", "name": "n3", "status": "terminating"},  # going: settled, no call
                           {"sailbox_id": "sb_f4", "name": "n4", "status": "sleeping"},     # its terminate is refused
                           {"sailbox_id": "sb_f5", "name": "n5", "status": "terminated"}]
        self.refuse_terminate("sb_f4")
        pool = self.pool()
        self.assertEqual(pool.reconcile(), 1)
        self.assertEqual(self.sail.terminated, ["sb_f2"])
        self.assertEqual({i: self.state(f"sb_f{i}") for i in range(1, 6)},
                         {1: "stopping", 2: "terminated", 3: "stopping", 4: "stopping", 5: "terminated"})
        self.assertEqual(sorted(a["box"] for a in self.actions("row_settled")), ["sb_f5"])
        self.assertEqual([a["box"] for a in self.actions("row_box_ended")], ["sb_f2"])
        self.assertEqual([a["box"] for a in self.actions("row_stop_requested")], ["sb_f4"])
        del self.sail.terminate  # Sail takes the call again
        pool.reconcile()
        self.assertEqual(self.state("sb_f4"), "terminated", "the next pass tries again")

    def test_a_list_that_may_be_cut_short_proves_nothing_absent(self):
        self.store.upsert_box("sb_f1", kind="gym", version="sbcp_11111111-aaaa", state="failed", detail={})
        self.sail.extra = [{"sailbox_id": f"sb_other{i}", "name": f"other-{i}", "status": "running"} for i in range(2)]
        pool = self.pool()
        with mock.patch.object(pool_mod, "LIST_LIMIT", 2):
            pool.reconcile()
        self.assertEqual(self.state("sb_f1"), "failed")
        pool.reconcile()
        self.assertEqual(self.state("sb_f1"), "stopping", "absence still supplies no terminal status")

    def test_a_live_row_adopt_could_not_take_back_is_ended_and_terminated(self):
        image = "sbcp_11111111-aaaa"
        for box_id in ("sb_good", "sb_stale", "sb_gone"):
            self.store.upsert_box(box_id, kind="gym", version=image, state="asleep", detail={"name": f"n-{box_id}"})
        self.sail.extra = [{"sailbox_id": "sb_good", "name": "n-sb_good", "status": "sleeping"},
                           {"sailbox_id": "sb_stale", "name": "n-sb_stale", "status": "sleeping"}]
        self.clock.advance(3600)

        def factory(client, box_id):
            if box_id != "sb_good":
                raise RuntimeError("no driver")
            return FakeDriver(client, box_id)

        pool = GymPool(self.store, self.sail, settings(), clock=self.clock, threaded=False, driver_factory=factory)
        self.assertEqual(pool.adopt(), 1)
        self.assertEqual(self.sail.terminated, ["sb_stale"], "the box Sail still keeps is ended; the adopted one is not")
        self.assertEqual((self.state("sb_good"), self.state("sb_stale"), self.state("sb_gone")),
                         ("asleep", "terminated", "stopping"))
        self.assertEqual([(a["box"], a["was"]) for a in self.actions("row_box_ended")], [("sb_stale", "asleep")])
        self.assertEqual(self.actions("row_settled"), [])

    def test_live_rows_wait_for_adopt_and_the_grace(self):
        self.store.upsert_box("sb_row", kind="gym", version="sbcp_11111111-aaaa", state="ready", detail={})
        self.clock.advance(3600)
        pool = self.pool()
        pool.reconcile()
        self.assertEqual(self.state("sb_row"), "ready", "before adopt a row the pool does not hold may still be adopted")
        pool._adopted = True
        self.store.upsert_box("sb_young", kind="gym", version="sbcp_11111111-aaaa", state="starting", detail={})
        pool.reconcile()
        self.assertEqual((self.state("sb_row"), self.state("sb_young")), ("stopping", "starting"),
                         "a row made within the grace may be a fork whose answer is still on its way")


class Lifecycle(PoolCase):
    """Dispatch uncertainty and runtime stops never invent a refund or consume a research attempt."""

    def actions(self, pool):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.pool"]

    def test_two_inadmissible_dispatchers_ignore_peer_notifications_until_their_backoff(self):
        pool = self.pool(batch_wait_seconds=0)
        boxes = [self.ready_box(pool), self.ready_box(pool)]
        queued = pool.submit(job("queued"))
        self.clock.advance(3000)  # valid commitment, but less lifetime left than a complete batch needs
        taken = []
        rejected_batches = []
        original = pool._take

        def take(box):
            taken.append(box.id)
            batch = original(box)
            if batch:
                rejected_batches.append(box.id)
            return batch

        pool._take = take
        threads = [threading.Thread(target=pool._serve, args=(box,)) for box in boxes]
        try:
            for thread in threads:
                thread.start()
            end = time.monotonic() + .15
            while time.monotonic() < end:
                with pool._wake:
                    pool._wake.notify_all()
                threading.Event().wait(.002)
            self.assertLessEqual(len(rejected_batches), 2, "notifications cannot remove a box's minimum retry delay")
            self.assertLessEqual(len(taken), 8, "only initial queue handoff races may yield empty takes")
            self.assertEqual((queued.attempts, queued.done.is_set(), pool.queued()), (0, False, 1))
            self.assertEqual(self.calls, [])
            self.assertEqual(self.sail.resumed, [])
            self.assertLessEqual(sum(p.get("action") == "compute_deferred" for p in self.actions(pool)), 2)
        finally:
            with pool._wake:
                pool._stopping = True
                pool._wake.notify_all()
            for thread in threads:
                thread.join(2)
            self.assertFalse(any(thread.is_alive() for thread in threads))

    def test_dispatcher_backoff_remains_retryable_for_a_later_covered_batch(self):
        pool = self.pool(batch_wait_seconds=0)
        box = self.ready_box(pool)
        queued = pool.submit(job())
        self.clock.advance(3000)
        thread = threading.Thread(target=pool._serve, args=(box,))
        try:
            thread.start()
            end = time.monotonic() + 1
            while box.compute_retry_at == 0 and time.monotonic() < end:
                threading.Event().wait(.005)
            self.assertGreater(box.compute_retry_at, time.monotonic())
            pool.settings["gym"]["run_timeout_seconds"] = 300  # genuinely fits the already reserved remaining lifetime
            with pool._wake:
                pool._wake.notify_all()
            self.assertTrue(queued.done.wait(2))
            self.assertIsNone(queued.error)
            self.assertEqual(queued.attempts, 0)
            self.assertEqual(len(self.calls), 1)
        finally:
            with pool._wake:
                pool._stopping = True
                pool._wake.notify_all()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def lost_create(self, pool):
        real = self.sail.from_checkpoint

        def lost(checkpoint, **kwargs):
            row = real(checkpoint, **kwargs)
            raise TimeoutError("the provider created the resource but its response was lost")

        self.sail.from_checkpoint = lost
        pool._start_box("gym")
        [(_, box)] = self.sail.forks
        [key] = self.store.get("compute_holds")
        self.assertIsNone(self.store.get("compute_holds")[key]["box_id"])
        return box, key

    def test_expired_idle_lease_is_stopped_before_capacity_is_replaced_without_a_trial(self):
        pool = self.pool(start_boxes=1, max_boxes=1, batch_wait_seconds=0)
        box = self.ready_box(pool)
        box.state = "asleep"
        queued = pool.submit(job())
        self.clock.advance(3600)
        out = pool.manage()
        self.assertEqual(box.state, "terminated")
        self.assertEqual(self.sail.terminated, [box.id])
        self.assertEqual(out["terminated"], 1)
        self.assertEqual(len(self.sail.forks), 1, "the ended finite lease no longer occupies the only slot")
        self.assertEqual((queued.attempts, queued.done.is_set(), pool.queued()), (0, False, 1))
        self.assertEqual(self.calls, [])
        held = next(r for r in self.store.get("compute_holds").values() if r.get("box_id") == box.id)
        self.assertTrue(held["confirmed_stopped"])
        self.assertFalse(held["billing_reconciled"])

    def test_expired_lease_with_unknown_stop_response_does_not_free_capacity(self):
        pool = self.pool(start_boxes=1, max_boxes=1)
        box = self.ready_box(pool)
        pool.submit(job())
        self.clock.advance(3600)
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "terminating"}
        out = pool.manage()
        self.assertEqual(box.state, "stopping")
        self.assertEqual(out["terminated"], 0)
        self.assertEqual(self.sail.forks, [])
        self.assertTrue(self.store.boxes(live=False)[0]["detail"]["cost_cursor"]["awake"])

    def test_lost_create_alias_and_uncertain_stop_survive_restart_without_freeing_budget(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "terminating"}
        self.clock.advance(400)
        self.assertEqual(pool.reconcile(), 0)
        held = self.store.get("compute_holds")[key]
        self.assertEqual(held["box_id"], box)
        self.assertFalse(held["confirmed_stopped"])
        reopened = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(reopened.close)
        again = GymPool(reopened, self.sail, settings(), clock=self.clock, threaded=False)
        again.adopt()
        row = next(r for r in reopened.boxes(live=False) if r["id"] == box)
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertFalse(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])
        self.assertFalse(row["detail"]["cost_cursor"]["billing_stop_confirmed"])
        self.assertGreater(compute.remaining(reopened, now=self.clock()), 0)
        self.assertEqual(self.sail.resumed, [])
        self.sail.terminated.append(box)  # an explicit matching inventory observation, not absence
        again.reconcile()
        self.assertTrue(reopened.get("compute_holds")[key]["confirmed_stopped"])
        self.assertFalse(reopened.get("compute_holds")[key]["billing_reconciled"])
        self.assertGreater(compute.remaining(reopened, now=self.clock()), 0)

    def test_terminal_inventory_for_a_lost_create_attaches_the_original_hold_without_another_stop(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.sail.terminated.append(box)
        self.clock.advance(400)
        self.assertEqual(pool.reconcile(), 1)
        self.assertEqual(self.sail.terminated, [box])
        held = self.store.get("compute_holds")[key]
        self.assertEqual(held["box_id"], box)
        self.assertTrue(held["confirmed_stopped"])
        self.assertFalse(held["billing_reconciled"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)

    def test_malformed_fork_response_never_attaches_none_or_dispatches_a_driver(self):
        pool = self.pool()
        queued = pool.submit(job())
        self.sail.from_checkpoint = lambda *args, **kwargs: {"status": "running"}
        pool._start_box("gym")
        [held] = self.store.get("compute_holds").values()
        self.assertIsNone(held["box_id"])
        self.assertFalse(held["confirmed_stopped"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)
        self.assertNotIn("None", pool.boxes)
        self.assertEqual(self.calls, [])
        self.assertEqual((queued.attempts, queued.done.is_set(), pool.queued()), (0, False, 1))

    def test_dispatch_lock_delay_reduces_the_ttl_sent_to_the_provider(self):
        pool = self.pool()
        mark = compute.mark_dispatched
        fork = self.sail.from_checkpoint
        sent = []

        def delayed(store, key):
            self.clock.advance(30)
            return mark(store, key)

        def observe(checkpoint, **kwargs):
            sent.append(kwargs["max_lifetime_seconds"])
            return fork(checkpoint, **kwargs)

        self.sail.from_checkpoint = observe
        with mock.patch.object(compute, "mark_dispatched", side_effect=delayed):
            pool._start_box("gym")
        self.assertEqual(sent, [3570], "a lock wait cannot push the resource past its reserved work deadline")

    def test_malformed_stray_id_never_reaches_provider_control(self):
        pool = self.pool()
        self.sail.extra = [{"sailbox_id": "None", "name": f"{pool.name_prefix('gym')}1-1", "status": "running"}]
        self.assertEqual(pool.reconcile(), 0)
        self.assertEqual(self.sail.terminated, [])
        self.assertEqual(self.store.boxes(live=False), [])
        self.assertTrue(any(p["action"] == "stray_stop_unresolved" for p in self.actions(pool)))

    def test_uncovered_legacy_stray_is_tracked_after_lost_stop_and_keeps_unknown_billing(self):
        import math

        pool = self.pool()
        box = "sb_abcd0123"
        self.sail.extra = [{"sailbox_id": box, "name": f"{pool.name_prefix('gym')}1-1", "status": "running"}]
        self.sail.terminate = mock.Mock(side_effect=TimeoutError("lost stop response"))
        self.assertEqual(pool.reconcile(), 0)
        [row] = self.store.boxes(live=False)
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        self.sail.extra[0]["status"] = "terminated"
        pool.reconcile()
        [row] = self.store.boxes(live=False)
        self.assertEqual(row["state"], "terminated")
        self.assertTrue(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])
        self.assertFalse(row["detail"]["cost_cursor"]["billing_stop_confirmed"])
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))

    def test_wrong_resource_stop_response_never_confirms_a_terminal_state(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.sail.terminate = lambda box_id: {"sailbox_id": "sb_ffffffff", "status": "terminated"}
        self.assertFalse(pool._request_stop(box, operation="terminate", why="synthetic"))
        self.assertEqual(box.state, "stopping")
        [row] = self.store.boxes(live=False)
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertFalse(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])

    def test_matching_failed_stop_responses_keep_the_runtime_and_billing_unresolved(self):
        pool = self.pool()
        box = self.ready_box(pool)
        for status in ("failed", "create_failed"):
            with self.subTest(status=status):
                self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": status}
                self.clock.advance(10)
                self.assertFalse(pool._request_stop(box, operation="terminate", why="synthetic failed status"))
                row = next(r for r in self.store.boxes(live=False) if r["id"] == box.id)
                cursor = row["detail"]["cost_cursor"]
                self.assertEqual((box.state, row["state"]), ("stopping", "stopping"))
                self.assertTrue(cursor["awake"])
                self.assertFalse(cursor["runtime_stop_confirmed"])
                self.assertFalse(cursor["billing_stop_confirmed"])
                self.assertIsNone(cursor["unresolved_billing_interval"]["end"])
                hold = next(r for r in compute._holds(self.store).values() if r["box_id"] == box.id)
                self.assertFalse(hold["confirmed_stopped"])
                self.assertFalse(hold["billing_reconciled"])

    def test_matching_failed_inventory_keeps_pending_stop_and_cursor_after_restart(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "terminating"}
        self.assertFalse(pool._request_stop(box, operation="terminate", why="synthetic pending stop"))
        interval_start = self.store.boxes(live=False)[0]["detail"]["cost_cursor"]["unresolved_billing_interval"]["start"]
        for status in ("failed", "create_failed"):
            with self.subTest(status=status):
                self.clock.advance(30)
                self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": status}
                self.assertEqual(pool._settle_rows([{"sailbox_id": box.id, "status": status}], grace=0), 0)
                row = self.store.boxes(live=False)[0]
                cursor = row["detail"]["cost_cursor"]
                self.assertEqual(row["state"], "stopping")
                self.assertTrue(cursor["awake"])
                self.assertFalse(cursor["runtime_stop_confirmed"])
                self.assertFalse(cursor["billing_stop_confirmed"])
                self.assertEqual(cursor["unresolved_billing_interval"]["start"], interval_start)
                self.assertIsNone(cursor["unresolved_billing_interval"]["end"])
        reopened = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(reopened.close)
        again = GymPool(reopened, self.sail, settings(), clock=self.clock, threaded=False)
        again.adopt()
        row = reopened.boxes(live=False)[0]
        self.assertEqual((again.boxes[box.id].state, row["state"]), ("stopping", "stopping"))
        self.assertGreater(compute.remaining(reopened, now=self.clock()), 0)
        self.assertEqual(self.sail.resumed, [])
        self.assertEqual([e for e in self.actions(pool) if e["action"] == "stop_confirmed"], [])

    def test_failed_lost_create_inventory_does_not_confirm_a_runtime_stop(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.clock.advance(400)
        self.sail.states[box] = "failed"
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "failed"}
        self.assertEqual(pool.reconcile(), 0)
        hold = compute._holds(self.store)[key]
        self.assertEqual(hold["box_id"], box)
        self.assertFalse(hold["confirmed_stopped"])
        self.assertFalse(hold["billing_reconciled"])
        row = self.store.boxes(live=False)[0]
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertFalse(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])

    def test_cleanup_failed_inventory_keeps_pending_ownership_until_documented_termination(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.store.put("forking", {key: self.clock()})
        self.sail.terminate = mock.Mock(return_value={"sailbox_id": box, "status": "failed"})
        for status in ("failed", "create_failed"):
            with self.subTest(status=status):
                self.sail.states[box] = status
                out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
                self.assertEqual((out["requested"], out["confirmed"], out["pending"]), (1, 0, 1))
                self.assertIn(key, self.store.get("forking"))
                self.assertFalse(compute._holds(self.store)[key]["confirmed_stopped"])
                self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)
                row = self.store.boxes(live=False)[0]
                self.assertEqual(row["state"], "stopping")
                self.assertTrue(row["detail"]["cost_cursor"]["awake"])
                self.assertFalse(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])

    def test_cleanup_lost_create_and_lost_stop_are_bound_and_tracked_across_restart(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.store.put("forking", {key: self.clock()})
        self.sail.terminate = mock.Mock(side_effect=TimeoutError("lost cleanup stop response"))
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["confirmed"], out["pending"]), (0, 1))
        self.assertTrue(out["errors"])
        self.assertEqual(compute._holds(self.store)[key]["box_id"], box)
        row = self.store.boxes(live=False)[0]
        cursor = row["detail"]["cost_cursor"]
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(cursor["awake"])
        self.assertFalse(cursor["runtime_stop_confirmed"])
        self.assertFalse(cursor["billing_stop_confirmed"])
        reopened = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(reopened.close)
        again = GymPool(reopened, self.sail, settings(), clock=self.clock, threaded=False)
        again.adopt()
        self.assertEqual(again.boxes[box].state, "stopping")
        self.assertEqual(self.sail.resumed, [])
        self.assertGreater(compute.remaining(reopened, now=self.clock()), 0)
        self.sail.terminated.append(box)
        self.clock.advance(20)
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["confirmed"], out["pending"]), (1, 0))
        self.assertTrue(compute._holds(reopened)[key]["confirmed_stopped"])
        self.assertFalse(compute._holds(reopened)[key]["billing_reconciled"])
        self.assertGreater(compute.remaining(reopened, now=self.clock()), 0)

    def test_cleanup_missing_inventory_preserves_stop_intent_and_ongoing_cursor(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.clock.advance(10)
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["inspected"], out["requested"], out["confirmed"]), (1, 0, 0))
        self.assertEqual(self.sail.terminated, [])
        row = self.store.boxes(live=False)[0]
        self.assertEqual(row["state"], "stopping")
        cursor = row["detail"]["cost_cursor"]
        self.assertTrue(cursor["awake"])
        self.assertFalse(cursor["runtime_stop_confirmed"])
        self.assertIsNone(cursor["unresolved_billing_interval"]["end"])
        began = cursor["unresolved_billing_interval"]["start"]
        self.clock.advance(30)
        cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        cursor = self.store.boxes(live=False)[0]["detail"]["cost_cursor"]
        self.assertEqual(cursor["unresolved_billing_interval"]["start"], began)
        self.assertAlmostEqual(self.store.spent(["gym_box"]), 40 * 0.20 / 3600.0)
        again = GymPool(self.store, self.sail, settings(), clock=self.clock, threaded=False)
        again.adopt()
        self.assertEqual(again.boxes[box.id].state, "stopping")
        self.assertEqual(self.sail.resumed, [])

    def test_cleanup_transitional_inventory_records_stop_intent_without_another_request(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.store.put("forking", {key: self.clock()})
        self.sail.states[box] = "terminating"
        self.sail.terminate = mock.Mock(side_effect=AssertionError("already transitioning"))
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["requested"], out["confirmed"], out["pending"]), (0, 0, 1))
        self.sail.terminate.assert_not_called()
        row = self.store.boxes(live=False)[0]
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertFalse(compute._holds(self.store)[key]["confirmed_stopped"])

    def test_cleanup_unreadable_inventory_persists_known_stop_intent_without_provider_control(self):
        pool = self.pool()
        box = self.ready_box(pool)
        self.sail.list_boxes = mock.Mock(side_effect=TimeoutError("inventory lost"))
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["inspected"], out["requested"], out["confirmed"]), (1, 0, 0))
        self.assertTrue(out["errors"])
        self.assertEqual(self.sail.terminated, [])
        row = self.store.boxes(live=False)[0]
        self.assertEqual(row["state"], "stopping")
        self.assertTrue(row["detail"]["cost_cursor"]["awake"])
        self.assertFalse(row["detail"]["cost_cursor"]["runtime_stop_confirmed"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)

    def test_cleanup_terminal_observation_preserves_first_stop_and_never_refunds_a_bill(self):
        pool = self.pool()
        box, key = self.lost_create(pool)
        self.store.put("forking", {key: self.clock()})
        self.sail.terminated.append(box)
        first = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((first["requested"], first["confirmed"], first["pending"]), (0, 1, 0))
        stop = compute._holds(self.store)[key]["stopped_observed_at"]
        interval = self.store.boxes(live=False)[0]["detail"]["cost_cursor"]["unresolved_billing_interval"]
        self.clock.advance(4000)  # a later read beyond the admitted deadline is not a later actual stop
        again = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual(again["confirmed"], 1)
        self.assertEqual(compute._holds(self.store)[key]["stopped_observed_at"], stop)
        self.assertFalse(compute._holds(self.store)[key].get("breached", False))
        self.assertEqual(self.store.boxes(live=False)[0]["detail"]["cost_cursor"]["unresolved_billing_interval"], interval)
        self.assertFalse(compute._holds(self.store)[key]["billing_reconciled"])
        self.assertGreater(compute.remaining(self.store, now=self.clock()), 0)

    def test_cleanup_malformed_inventory_cannot_control_or_bind_a_resource(self):
        pool = self.pool()
        name = pool.name_prefix("gym") + "1-1"
        self.store.put("forking", {name: self.clock()})
        self.sail.extra = [{"sailbox_id": "None", "name": name, "status": "running"}]
        out = cleanup_stopped(self.store.root, self.sail, clock=self.clock)
        self.assertEqual((out["requested"], out["confirmed"], out["pending"]), (0, 0, 1))
        self.assertTrue(out["errors"])
        self.assertEqual(self.sail.terminated, [])
        self.assertEqual(self.store.boxes(live=False), [])

    def test_alias_conflict_does_not_rebind_or_hide_the_second_resource_bill(self):
        import math

        pool = self.pool()
        first, key = self.lost_create(pool)
        compute.attach(self.store, key, first)
        second = "sb_abc10001"
        self.sail.extra = [{"sailbox_id": second, "name": key, "status": "running"}]
        self.sail.terminate = lambda box_id: {"sailbox_id": box_id, "status": "terminating"}
        self.clock.advance(400)
        pool.reconcile()
        self.assertEqual(compute._holds(self.store)[key]["box_id"], first)
        self.assertEqual({r["id"] for r in self.store.boxes(live=False)}, {first, second})
        self.assertTrue(math.isinf(compute.remaining(self.store, now=self.clock())))
        self.assertEqual(compute._legacy(self.store)[second]["usd"], None)
        self.assertFalse(compute._legacy(self.store)[second]["billing_reconciled"])
        self.assertTrue(any(e["action"] == "compute_alias_conflict" for e in self.actions(pool)))


if __name__ == "__main__":
    unittest.main()

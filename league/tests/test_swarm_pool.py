"""The Gym pool (league/swarm/pool.py): sealed forks of the Gym image, day-major batches, sleep, version change,
the guard's brake, and failures that never kill the pool. A fake Sail and a fake Gym driver."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.pool import Box, GymJob, GymPool, PoolError
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail


def settings(**gym):
    out = copy.deepcopy(S.DEFAULTS)
    out["gym"].update({"enabled": True, "image_checkpoint": "sbcp_11111111-aaaa", "gate_checkpoint": "sbcp_22222222-bbbb",
                       "batch_wait_seconds": 8, "batch_programs": 3, **gym})
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
        box = Box(f"sb_{len(pool.boxes) + 1:08d}-ffff-ffff-ffff-ffffffffffff", kind, str(image), "ready",
                  driver=FakeDriver(self.sail, "x", calls=self.calls, fail=lambda: self.failure), roots=("SPY", "QQQ", "IWM", "XSP", "SPXW"),
                  last_used=self.clock())
        pool.boxes[box.id] = box
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
            def from_checkpoint(self, checkpoint, *, name, timeout=900.0):
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
        self.assertEqual(len(self.sail.forks), 4)

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
        self.sail.extra = [{"sailbox_id": "sb_stray", "name": f"ltcm-swarm-{pool.token}-gym-1-9", "status": "running", "created_at": old},
                           {"sailbox_id": "sb_trial", "name": "ltcm-swarm-0a0a0a-gym-1-9", "status": "running", "created_at": old},
                           {"sailbox_id": "sb_young", "name": f"ltcm-swarm-{pool.token}-gym-2-9", "status": "running",
                            "created_at": self.clock() - 30},
                           {"sailbox_id": "sb_w1", "name": "ltcm-gym-image-v1", "status": "running"},
                           {"sailbox_id": "sb_house", "name": "ltcm-floor", "status": "running"}]
        pool.adopt()
        self.assertEqual(self.sail.terminated, ["sb_stray"], "another store's boxes and a box made minutes ago are left alone")

    def test_boxes_named_before_the_token_are_adopted_when_known_and_ended_when_stray(self):
        """Stage 1 named its boxes `ltcm-swarm-<kind>-<epoch>-<n>` (no token): the release after it takes them over."""
        old = int(self.clock()) - 3600
        self.store.upsert_box("sb_known", kind="gym", version="sbcp_11111111-aaaa", state="asleep",
                              detail={"name": f"ltcm-swarm-gym-{old}-1"})
        self.sail.extra = [{"sailbox_id": "sb_known", "name": f"ltcm-swarm-gym-{old}-1", "status": "sleeping"},
                           {"sailbox_id": "sb_lost", "name": f"ltcm-swarm-gym-{old}-2", "status": "running"},
                           {"sailbox_id": "sb_gate", "name": f"ltcm-swarm-gate-{old}-3", "status": "running"},
                           {"sailbox_id": "sb_new", "name": f"ltcm-swarm-gym-{int(self.clock()) - 60}-4", "status": "running"},
                           {"sailbox_id": "sb_other", "name": f"ltcm-swarm-0a0a0a-gym-{old}-1", "status": "running"},
                           {"sailbox_id": "sb_w1", "name": "ltcm-gym-image-v1", "status": "running"}]
        pool = self.pool()
        self.assertEqual(pool.adopt(), 1)
        self.assertEqual(pool.boxes["sb_known"].state, "asleep", "a box the store knows is adopted, whatever its name")
        self.assertEqual(sorted(self.sail.terminated), ["sb_gate", "sb_lost"], "untokened strays older than the grace end")

    def test_stopping_sleeps_busy_boxes_too_the_brake_does_not(self):
        pool = self.pool()
        box = self.ready_box(pool)
        box.state = "busy"
        self.assertEqual(pool.scale_to_zero("brake"), 0, "the guard's brake lets a running batch finish")
        self.assertEqual(pool.scale_to_zero("stopped", busy=True), 1, "a stopping process loses the batch anyway")
        self.assertEqual(self.sail.slept, [box.id])

    def test_the_cap_counts_the_stores_live_boxes_too(self):
        for i in range(6):
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
        self.assertEqual(self.store.boxes(live=False)[0]["state"], "failed")
        self.assertEqual(self.sail.terminated, [box.id])
        self.assertEqual(len(pool.queue), 1, "its job goes back to the queue")

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
        self.clock.advance(3600)
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
        real = self.sail.from_checkpoint

        def slow_post(checkpoint, *, name, timeout=900.0):
            release.wait(5)
            return real(checkpoint, name=name)

        self.sail.from_checkpoint = slow_post
        pool = GymPool(self.store, self.sail, settings(start_boxes=1), clock=self.clock, threaded=True,
                       driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls))
        pool.submit(job("a"))
        pool.manage()
        threading.Timer(0.2, release.set).start()
        pool.stop(join_seconds=5)
        self.assertFalse(any(t.is_alive() for t in pool.fork_threads), "no fork outlives the pool")
        self.assertEqual([b.state for b in pool.boxes.values()], ["asleep"])
        self.assertEqual(self.sail.slept, [self.sail.forks[0][1]])

    def test_a_fork_in_flight_is_never_taken_for_a_stray(self):
        sail = self.sail
        pool = self.pool(start_boxes=1)
        real = sail.from_checkpoint

        def slow_post(checkpoint, *, name, timeout=900.0):
            row = real(checkpoint, name=name)  # Sail has made the box; the POST has not returned yet
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
        pool = GymPool(self.store, self.sail, settings(start_boxes=1, batch_wait_seconds=0), threaded=True,
                       driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls))
        self.addCleanup(pool.stop)
        j = pool.submit(job("a"))
        pool.manage()
        self.assertEqual(pool.wait(j, 10)["status"], "ok")


if __name__ == "__main__":
    unittest.main()

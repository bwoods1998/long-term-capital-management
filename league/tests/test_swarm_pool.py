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

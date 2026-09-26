"""Post-burst integration: actual router/pool admission, owned cleanup and maintenance scheduling."""
import concurrent.futures
import threading
from unittest import mock

from league.swarm.architect import Architect
from league.swarm.lifecycle import BudgetDeferred
from league.swarm.loop import Swarm
from league.swarm.models import ModelRouter
from league.swarm.pool import GymJob, GymPool, cleanup_stopped
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import FakeDriver, FakeSail, response_payload
from league.tests.test_swarm_lifecycle import LifeCase, epoch


class Resources(FakeSail):
    dimensions = {"vcpu_count": 8, "memory_mib": 32768, "state_disk_size_gib": 256}

    def __init__(self):
        super().__init__()
        self.states = {}
        self.sleep_lost = False
        self.terminate_lost = False
        self.fork_lost = False
        self.oversized = False

    def from_checkpoint(self, checkpoint, **kwargs):
        row = super().from_checkpoint(checkpoint, **kwargs)
        self.states[row["sailbox_id"]] = "running"
        if self.fork_lost:
            raise TimeoutError("POST answer lost")
        return row

    def get(self, box):
        return {"sailbox_id": box, "name": self.names.get(box), "status": self.states.get(box, "running"),
                **self.dimensions, **({"vcpu_count": 9} if self.oversized else {})}

    def list_boxes(self, **kwargs):
        return [self.get(box) for box in self.names]

    def sleep(self, box, **kwargs):
        super().sleep(box, **kwargs)
        if self.sleep_lost:
            raise TimeoutError("sleep outcome unknown")
        self.states[box] = "sleeping"

    def resume(self, box, **kwargs):
        super().resume(box, **kwargs)
        self.states[box] = "running"

    def terminate(self, box):
        super().terminate(box)
        if self.terminate_lost:
            raise TimeoutError("termination outcome unknown")
        self.states[box] = "terminated"


class PoolWork(LifeCase):
    def setUp(self):
        super().setUp()
        self.family("f")
        self.budget.refresh()
        self.cfg["gym"].update(enabled=True, image_checkpoint="sbcp_gym", gate_checkpoint="sbcp_gate")
        self.api = Resources()
        self.calls = []
        self.pool = GymPool(self.store, self.api, self.cfg, clock=self.clock, threaded=False,
                            driver_factory=lambda api, box: FakeDriver(api, box, calls=self.calls))
        self.store.put("checkpoint_capacities", {"sbcp_gym": self.api.dimensions, "sbcp_gate": self.api.dimensions})

    def job(self, *, forward=False):
        return GymJob(family="f", version=1, code="NEEDS = {}", params={}, window="forward" if forward else "train",
                      roots=("SPY",), purpose="forward" if forward else "train", gate="forward" if forward else None)

    def test_a_successful_batch_reserves_before_resume_and_sleeps_before_releasing(self):
        self.pool._start_box("gym")
        box = next(iter(self.pool.boxes.values()))
        first = box.budget_key
        original = box.driver.run
        def run(*args, **kwargs):
            self.assertEqual(self.store._one("SELECT state FROM sail_commitments WHERE key=?", (box.budget_key,))["state"], "open")
            self.clock.advance(30)
            return original(*args, **kwargs)
        box.driver.run = run
        job = self.job()
        self.pool.run_batch(box, [job])
        self.assertTrue(job.done.is_set())
        self.assertEqual(self.api.states[box.id], "sleeping")
        self.assertEqual(box.state, "asleep")
        self.assertNotEqual(first, box.budget_key)
        self.assertEqual(self.budget.status()["held_usd"], 0)
        self.assertAlmostEqual(self.budget.status()["actual_usd"], .012 + .6*30/3600)

    def test_same_second_restart_cannot_reuse_a_lost_forks_reservation(self):
        self.api.fork_lost = True
        self.pool._start_box("gym")
        other = GymPool(self.store, self.api, self.cfg, clock=self.clock, threaded=False)
        other._start_box("gym")
        self.assertEqual(len(set(self.api.names.values())), 2)
        self.assertEqual(len(self.store._all("SELECT key FROM sail_commitments WHERE state='open'")), 2)

    def test_config_change_cannot_extend_an_open_box_lease(self):
        self.pool._start_box("gym")
        box = next(iter(self.pool.boxes.values()))
        deadline = self.pool._deadline(box.id)
        self.cfg["lifecycle"]["box_lease_seconds"] = 86400
        self.assertEqual(self.pool._deadline(box.id), deadline)

    def test_unknown_sleep_prevents_another_dispatch_and_retains_the_hold(self):
        self.pool._start_box("gym")
        box = next(iter(self.pool.boxes.values()))
        self.api.sleep_lost = True
        job = self.job()
        self.pool.run_batch(box, [job])
        self.assertIn("cannot verify", job.error)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.api.resumed, [])
        self.assertGreater(self.budget.status()["held_usd"], 0)
        self.api.sleep_lost = False
        self.pool._sleep(box)
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_oversized_fork_has_no_work_and_keeps_hold_until_confirmed_end(self):
        self.api.oversized = True
        self.api.terminate_lost = True
        self.pool._start_box("gym")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.pool.boxes, {})
        self.assertGreater(self.budget.status()["held_usd"], 0)
        box = self.api.forks[0][1]
        self.api.states[box] = "terminated"
        self.pool.reconcile()
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_lost_fork_is_charged_until_exact_owned_name_is_confirmed_ended(self):
        self.api.fork_lost = True
        self.pool._start_box("gym")
        self.assertEqual(self.pool.boxes, {})
        self.assertGreater(self.budget.status()["held_usd"], 0)
        other = "sb_unrelated"
        self.api.names[other] = "some-other-app"
        self.clock.advance(301)
        self.pool.reconcile()
        self.assertEqual(self.budget.status()["held_usd"], 0)
        self.assertGreaterEqual(self.budget.status()["actual_usd"], .412)
        self.assertNotIn(other, self.api.terminated)

    def test_stopped_cleanup_resolves_only_confirmed_owned_commitments(self):
        self.pool._start_box("gym")
        box = next(iter(self.pool.boxes.values()))
        self.api.terminate_lost = True
        out = cleanup_stopped(self.root, self.api)
        self.assertEqual(out["confirmed"], 0)
        self.assertGreater(self.budget.status()["held_usd"], 0)
        self.api.terminate_lost = False
        out = cleanup_stopped(self.root, self.api)
        self.assertEqual(out["confirmed"], 1)
        self.assertEqual(self.budget.status()["held_usd"], 0)
        self.assertEqual(self.api.states[box.id], "terminated")

    def test_floor_preserves_forward_work_and_defers_research_without_new_trial(self):
        state = self.store.get("lifecycle")
        self.store.put("lifecycle", {**state, "mode": "floor"})
        rejected = self.pool.submit(self.job())
        self.assertTrue(rejected.done.is_set())
        self.assertEqual(self.store.family("f")["trials"], 0)
        forward = self.pool.submit(self.job(forward=True))
        self.assertFalse(forward.done.is_set())
        self.pool._start_box("gate")
        box = next(iter(self.pool.boxes.values()))
        self.pool.run_batch(box, [forward])
        self.assertTrue(forward.done.is_set())
        self.assertIsNone(forward.error)
        self.assertEqual(self.budget.status()["held_usd"], 0)


class RouterWork(LifeCase):
    def setUp(self):
        super().setUp()
        from ltcm.provider import Provider
        self.family("f")
        self.budget.refresh()
        self.posts = []
        self.done = False
        self.error = None
        self.payload = {}
        def transport(method, route, body=None, idempotency_key=None):
            from ltcm.provider import ProviderError
            if method == "POST":
                self.posts.append(body)
                if self.error:
                    raise ProviderError(self.error)
                self.payload.update(response_payload(body["model"], text="ok"))
            if self.done:
                return self.payload
            return {"id": self.payload["id"], "model": self.payload["model"], "status": "in_progress"}
        self.provider = Provider(self.root / "p.sqlite", transport=transport, clock=self.clock,
                                 floor_cap_usd_per_day="100", poll_timeout=0, sleep=lambda _: None)
        self.addCleanup(self.provider.close)
        self.router = ModelRouter(self.store, self.provider, settings=self.cfg, sleep=lambda _: None)

    def ask(self, key="call"):
        return self.router.sail("k3_balanced", [{"role": "user", "content": "test"}], family="f", key=key, max_output=6000)

    def test_ambiguous_dispatch_can_settle_after_floor_without_a_second_paid_call(self):
        from ltcm.provider import ProviderError
        with self.assertRaises(ProviderError):
            self.ask()
        held = self.budget.status()["held_usd"]
        self.assertGreater(held, 0)
        self.store.put("lifecycle", {**self.store.get("lifecycle"), "mode": "floor"})
        self.done = True
        answer = self.ask()
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.budget.status()["held_usd"], 0)
        self.assertAlmostEqual(self.budget.status()["actual_usd"], float(answer.cost_usd))
        with self.assertRaises(BudgetDeferred):
            self.ask("new")

    def test_abandoned_request_must_reenter_admission_before_redispatch(self):
        from ltcm.provider import ProviderError
        self.error = "provider_transport_timeout"
        with self.assertRaises(ProviderError):
            self.ask()
        self.provider.reconcile_stale(now=self.clock()+3600)
        self.assertEqual(self.router._row("call")["status"], "abandoned")
        self.store.put("lifecycle", {**self.store.get("lifecycle"), "mode": "floor"})
        self.error = None
        self.done = True
        with self.assertRaises(BudgetDeferred):
            self.ask()
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_two_real_routers_share_admission_before_either_paid_dispatch(self):
        from ltcm.events import canonical
        from ltcm.provider import Provider, ProviderError
        other_store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other_store.close)
        other_provider = Provider(self.root / "second-provider.sqlite", clock=self.clock,
                                  floor_cap_usd_per_day="100", poll_timeout=0, sleep=lambda _: None,
                                  transport=self.provider.transport)
        self.addCleanup(other_provider.close)
        other = ModelRouter(other_store, other_provider, settings=self.cfg, sleep=lambda _: None)
        items = [{"role": "user", "content": "test"}]
        body = self.provider.build_body("k3_balanced", items, max_output_tokens=6000, cache_key="f", reasoning_effort="low")
        hold = float(self.provider.estimate("k3_balanced", len(canonical({"input": body["input"], "tools": body.get("tools", [])}).encode()), 6000))
        room = self.budget.status()["research_room_usd"]
        self.budget.reserve("other-known-work", room - hold*1.5, kind="gym_box")
        self.budget.charge("other-known-work", room - hold*1.5, final=True)
        barrier = threading.Barrier(2)
        def run(pair):
            router, key = pair
            barrier.wait()
            try:
                router.sail("k3_balanced", items, family="f", key=key, max_output=6000)
            except BudgetDeferred:
                return "deferred"
            except ProviderError:
                return "dispatched"
            self.fail("synthetic response remains ambiguous")
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            outcomes = list(executor.map(run, [(self.router, "first"), (other, "second")]))
        self.assertEqual(sorted(outcomes), ["deferred", "dispatched"])
        self.assertEqual(len(self.posts), 1)
        self.assertAlmostEqual(self.budget.status()["held_usd"], hold)


class Cadence(LifeCase):
    def test_daily_architect_is_claimed_before_ambiguous_dispatch_and_does_not_refill_over_16(self):
        for i in range(20):
            self.family(f"f{i}")
        router = mock.Mock()
        router.ask.side_effect = TimeoutError("answer unknown")
        architect = Architect(self.store, router, self.cfg, clock=self.clock)
        self.assertEqual(architect.want(), 0)
        self.assertFalse(architect.refilling())
        architect.run()
        restarted = Architect(self.store, router, self.cfg, clock=self.clock)
        self.assertFalse(restarted.due())
        restarted.run()
        self.assertEqual(router.ask.call_count, 1)
        self.assertEqual(len(self.store.families(alive=True)), 20)

    def test_floor_keeps_daily_architect_ideas_without_births(self):
        self.store.put("lifecycle", {**self.store.get("lifecycle"), "mode": "floor"})
        router = mock.Mock()
        rows = [{"mechanism": "Synthetic test proposal retained for later evaluation", "structure": "debit_vertical", "roots": ["SPY"]}]
        router.ask.return_value = {"json": {"families": rows}, "text": "private proposal"}
        result = Architect(self.store, router, self.cfg, clock=self.clock).run()
        self.assertEqual(result["born"], [])
        self.assertEqual(self.store.get("daily_architect")["proposals"], rows)
        self.assertEqual(self.store.families(), [])

    def test_floor_and_unavailable_research_gym_do_not_suppress_maintenance_rounds(self):
        self.store.put("lifecycle", {**self.store.get("lifecycle"), "mode": "floor"})
        router, pool, guard = mock.Mock(), mock.Mock(), mock.Mock()
        pool.bundle.return_value = "bundle"
        pool.unavailable.return_value = True
        guard.allows.return_value = True
        guard.due.return_value = False
        sw = Swarm(self.root, settings=self.cfg, config={}, store=self.store, router=router, pool=pool, guard=guard, clock=self.clock)
        sw.gate = mock.Mock()
        sw.architect = mock.Mock()
        sw._round = mock.Mock()
        sw._beat = self.clock()
        sw.step()
        self.assertEqual([call.args[0] for call in sw._round.call_args_list], ["forward", "architect"])
        self.assertEqual(sw.settings["gym"]["max_boxes"], 1)

    def test_post_burst_pace_starts_at_boundary_not_preopen_burst_spend(self):
        router, pool, guard = mock.Mock(), mock.Mock(), mock.Mock()
        sw = Swarm(self.root, settings=self.cfg, config={}, store=self.store, router=router, pool=pool, guard=guard, clock=self.clock)
        self.clock.t = epoch("2026-09-28T13:29:59Z")
        self.store.add_spend("sail_model", 50)
        self.assertTrue(sw.pace_status()["paused"])
        self.clock.advance(1)
        self.good()
        self.budget.refresh()
        status = sw.pace_status()
        self.assertEqual(status["spent_last_hour_usd"], 0)
        self.assertFalse(status["paused"])

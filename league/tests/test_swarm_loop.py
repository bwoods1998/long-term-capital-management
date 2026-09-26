"""The swarm's process (league/swarm/loop.py) with fakes: 48 founders seeded, 48 researchers each completing a cycle
concurrently, the main loop's rounds and the guard's brake, and the reasons it leaves. Plus the founders
themselves (league/swarm/seeds.py)."""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.loop import Scheduler, Swarm
from league.swarm.models import ModelRouter
from league.swarm.pool import GymPool
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.store import CLOSEABLE, STRUCTURES, SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail, provider

GYM = importlib.util.find_spec("league.gym") is not None


class Guard:
    def __init__(self):
        self.braked = False
        self.reason = ""
        self.last = {}
        self.checks = 0

    def allows(self, kind="any"):
        return not self.braked

    def due(self):
        return True

    def check(self):
        self.checks += 1
        return {}


def settings():
    s = copy.deepcopy(S.DEFAULTS)
    s["enabled"] = True
    s["gym"].update({"enabled": True, "image_checkpoint": "sbcp_gym", "gate_checkpoint": "sbcp_gate", "batch_wait_seconds": 0.2,
                     "start_boxes": 4, "max_boxes": 8})
    s["researcher"]["idle_seconds"] = 0
    return s


class LoopCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "state"
        self.root.mkdir()
        self.settings = settings()
        (self.root / "swarm.json").write_text(json.dumps({"enabled": True, "gym": self.settings["gym"],
                                                          "researcher": {"idle_seconds": 0}}))
        self.store = SwarmStore(self.root)
        self.addCleanup(self.store.close)
        self.provider, self.sail = provider(self.root / "p.sqlite", self.script)
        self.addCleanup(self.provider.close)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings)
        self.guard = Guard()
        self.box_sail = FakeSail()
        self.pool = GymPool(self.store, self.box_sail, self.settings, allowed=lambda k: self.guard.allows(k),
                            driver_factory=lambda client, box: FakeDriver(client, box))
        self.addCleanup(self.pool.stop)

    def script(self, body):
        return {"calls": [("notebook", {"action": "append", "text": "noted"})]} if len(body["input"]) < 6 else {"text": "ok"}

    def swarm(self):
        return Swarm(self.root, settings=self.settings, config={}, store=self.store, router=self.router, pool=self.pool,
                     guard=self.guard, sleep=lambda s: time.sleep(min(s, 0.05)))


class Process(LoopCase):
    def test_it_seeds_the_48_founders_once(self):
        sw = self.swarm()
        born = sw.seed()
        self.assertEqual(len(born), 48)
        self.assertEqual(sw.seed(), [])
        kinds = [e["kind"] for e in self.store.events_after(0)]
        self.assertEqual(kinds.count("swarm.born"), 48)

    def test_48_researchers_each_complete_a_cycle_concurrently(self):
        sw = self.swarm()
        sw.seed()
        self.pool.manage()  # forks the start boxes when there is work; nothing yet
        threads = []
        results = {}

        def one(fid):
            results[fid] = sw.researcher.cycle(fid)

        manager_stop = threading.Event()

        def manage():
            while not manager_stop.is_set():
                self.pool.manage()
                time.sleep(0.05)

        m = threading.Thread(target=manage, daemon=True)
        m.start()
        began = time.time()
        for fam in self.store.families(alive=True):
            t = threading.Thread(target=one, args=(fam["id"],))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(60)
        manager_stop.set()
        elapsed = time.time() - began
        self.assertEqual(len(results), 48)
        errors = {k: v.get("error") for k, v in results.items() if v.get("error")}
        self.assertEqual(errors, {})
        self.assertTrue(all(v.get("starter") for v in results.values()))
        self.assertLess(max(v["seconds"] for v in results.values()), 180)
        self.assertLess(elapsed, 60)
        self.assertEqual(self.store.totals()["trials"], 48)
        self.assertLessEqual(len(self.box_sail.forks), 8)
        self.assertGreaterEqual(len(self.box_sail.forks), 4)

    def test_a_step_checks_the_guard_manages_the_pool_starts_rounds_and_beats(self):
        sw = self.swarm()
        sw.seed()
        sw.step()
        self.assertEqual(self.guard.checks, 1)
        beat = json.loads((self.root / "swarm.heartbeat").read_text())
        self.assertEqual(beat["status"]["families_alive"], 48)
        self.assertIn("usd_per_hour", beat["status"])
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertNotIn("tournament", sw.rounds, "the first tournament is an hour after the founding")
        self.assertIn("gate", sw.rounds)
        self.store.put("tournament_at", 0.0)
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertIn("tournament", sw.rounds)
        self.assertGreater(self.store.get("tournament_at"), 0.0)

    def test_the_brake_scales_the_gym_to_zero_and_idles_researchers(self):
        sw = self.swarm()
        sw.seed()
        self.guard.braked = True
        self.guard.reason = "the Sail balance is under the House's line"
        sw.step()
        self.assertEqual(sw.rounds, {}, "no round starts under the brake")
        worker = threading.Thread(target=sw._worker, args=(0,), daemon=True)
        worker.start()
        time.sleep(0.3)
        sw.stop.set()
        worker.join(10)
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.cycle"], [], "no researcher cycles")
        self.assertEqual(self.box_sail.forks, [])

    def test_researchers_hold_while_the_last_hours_spend_is_at_the_pace(self):
        sw = self.swarm()
        sw.seed()
        self.settings["researcher"]["usd_per_hour"] = 1.0
        self.store.add_spend("sail_model", 1.2)
        self.assertTrue(sw.over_pace())
        worker = threading.Thread(target=sw._worker, args=(0,), daemon=True)
        worker.start()
        time.sleep(0.3)
        sw.stop.set()
        worker.join(10)
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.cycle"], [])

    def test_it_leaves_on_a_stop_file_or_a_new_release(self):
        sw = self.swarm()
        self.assertEqual(sw.should_stop(), "")
        (self.root / "swarm.stop").write_text("x")
        self.assertIn("swarm.stop", sw.should_stop())
        (self.root / "swarm.stop").unlink()
        (self.root.parent / "releases").mkdir()
        (self.root.parent / "releases" / "NEW").mkdir()
        (self.root.parent / "current").symlink_to(self.root.parent / "releases" / "NEW")
        self.assertIn("release changed", sw.should_stop())

    def test_a_second_swarm_will_not_run_while_one_holds_the_lock(self):
        import fcntl

        with open(self.root / "swarm.lock", "a+") as other:
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            sw = self.swarm()
            sw.lock_tries = 2
            self.assertEqual(sw.run(once=True), 0)
            self.assertEqual(self.store.families(), [], "it did nothing")
        sw = self.swarm()
        self.assertEqual(sw.run(once=True), 0)
        info = json.loads((self.root / "swarm.lock").read_text())
        self.assertEqual(info["pid"], __import__("os").getpid())
        self.assertIn("start", info)
        self.assertEqual(len(self.store.families()), 48)

    def test_the_first_heartbeat_comes_before_any_network_call(self):
        seen = []

        class SlowPool(GymPool):
            def adopt(inner):
                seen.append((self.root / "swarm.heartbeat").exists())
                return 0

        self.pool = SlowPool(self.store, self.box_sail, self.settings, allowed=lambda k: True,
                             driver_factory=lambda client, box: FakeDriver(client, box))
        self.swarm().run(once=True)
        self.assertEqual(seen, [True])

    def test_its_log_is_bounded(self):
        (self.root / "swarm.log").write_bytes(b"x" * 2000)
        self.swarm().bound_log(max_bytes=1000)
        self.assertLess((self.root / "swarm.log").stat().st_size, 1000)

    def test_run_once_and_stop(self):
        sw = self.swarm()
        self.assertEqual(sw.run(once=True), 0)
        self.assertEqual(len(self.store.families(alive=True)), 48)
        kinds = [e["payload"].get("action") for e in self.store.events_after(0) if e["kind"] == "swarm.status"]
        self.assertEqual(kinds, ["started", "stopped"])


class Scheduling(LoopCase):
    def test_one_cycle_a_family_at_a_time_and_the_bandits_favourites_first(self):
        for i in range(3):
            self.store.add_family({**family_spec(SEEDS[i])}, origin="seed")
        ids = [f["id"] for f in self.store.families()]
        self.store.update_family(ids[2], weight=0.8)
        self.store.update_family(ids[0], weight=0.1)
        self.store.update_family(ids[1], weight=0.1)
        clock = Clock()
        sched = Scheduler(self.store, clock=clock)
        first = sched.take(idle_seconds=0)
        self.assertEqual(first, ids[2])
        second = sched.take(idle_seconds=0)
        self.assertNotEqual(second, first)
        sched.release(first, {"error": "provider: BudgetExceeded provider_desk_cap"})
        clock.advance(10)
        self.assertNotIn(sched.take(idle_seconds=0), (first,))

    def test_an_erring_family_backs_off(self):
        self.store.add_family(family_spec(SEEDS[0]), origin="seed")
        clock = Clock()
        sched = Scheduler(self.store, clock=clock)
        fid = sched.take(idle_seconds=0)
        sched.release(fid, {"error": "TransportError"})
        self.assertIsNone(sched.take(idle_seconds=0))
        clock.advance(61)
        self.assertEqual(sched.take(idle_seconds=0), fid)


class Founders(unittest.TestCase):
    def test_48_distinct_families_with_a_mechanism_a_structure_and_a_slice(self):
        self.assertEqual(len(SEEDS), 48)
        self.assertEqual(len({s["id"] for s in SEEDS}), 48)
        founders = [s for s in SEEDS if s.get("founder")]
        self.assertEqual(len(founders), 12, "the twelve Deploy G structure founders, re-expressed")
        for s in SEEDS:
            self.assertRegex(s["id"], r"^[a-z0-9-]{1,40}$")
            self.assertIn(s["structure"], STRUCTURES)
            self.assertGreater(len(s["mechanism"]), 40)
            self.assertTrue(s["rejection"].startswith("Rejected if"))
            if set(s["roots"]) & {"XSP", "SPXW"}:
                self.assertNotIn(s["structure"], ("calendar", "diagonal"))
        self.assertGreaterEqual(len({s["structure"] for s in SEEDS}), 10)
        self.assertEqual({r for s in SEEDS for r in s["roots"]}, {"SPY", "QQQ", "IWM", "XSP", "SPXW"})
        self.assertGreaterEqual(sum(1 for s in SEEDS if s["structure"] in CLOSEABLE), 30)

    def test_every_starter_is_a_date_free_program(self):
        year = re.compile(r"(?<![0-9])20(?:19|2[0-9]|30)(?![0-9])")
        for s in SEEDS:
            code, params = program_for(s)
            tree = ast.parse(code)
            names = {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
            self.assertLessEqual({"NEEDS", "PARAMS"}, names, s["id"])
            self.assertIn("decide", {n.name for n in tree.body if isinstance(n, ast.FunctionDef)})
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    self.assertFalse(2019 <= node.value <= 2030, (s["id"], node.value))
            self.assertIsNone(year.search(code.split("\n", 3)[-1]), s["id"])
            self.assertEqual(program_for({**family_spec(s)}), (code.replace(f"# {s['id']}:", f"# {s['id']}:"), params))

    @unittest.skipUnless(GYM, "the Gym's own check")
    def test_every_starter_passes_the_gyms_safety_check(self):
        from league.gym.safety import check_program

        for s in SEEDS:
            check_program(program_for(s)[0])

    @unittest.skipUnless(GYM and importlib.util.find_spec("numpy") is not None, "numpy (requirements-gym.txt)")
    def test_every_starter_loads_in_the_gym(self):
        from league.gym.runtime import load_program

        for s in SEEDS:
            code, params = program_for(s)
            load_program(code, name=s["id"], params=params)


if __name__ == "__main__":
    unittest.main()

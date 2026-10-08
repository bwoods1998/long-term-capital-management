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
from league.swarm.guard import RESEARCH_KINDS
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
        self.research_held = False  # THE GATE'S RESERVE: new research is held, the gate's rounds go on (`SailGuard.allows`)
        self.held = ""
        self.last = {}
        self.checks = 0
        self.asked: list[str] = []

    def allows(self, kind="any"):
        self.asked.append(kind)
        return not self.braked and not (self.research_held and kind in RESEARCH_KINDS)

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
        self.threads_before = set(threading.enumerate())  # what was running before this fixture's pool (join_dispatchers)
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
        self.addCleanup(self.join_dispatchers)  # runs after the pool's stop, before the provider and the store close
        self.addCleanup(self.pool.stop)
        self.addCleanup(self.join_rounds)  # registered last, so it runs first: no round outlives the store it writes to

    @staticmethod
    def join_rounds(seconds=30):
        """Wait for the rounds a `Swarm.step` left running (`Swarm._round`'s threads, named round-<name>), however the test
        built its Swarm: one still running when the store closes fails in its thread with `Cannot operate on a closed
        database`, after the test that started it has passed."""
        for thread in threading.enumerate():
            if thread.name.startswith("round-"):
                thread.join(seconds)

    def join_dispatchers(self, seconds=30):
        """Wait for the pool's dispatchers (`GymPool._serve`'s threads, named gym-<box>) once the pool is stopped: `stop`
        tells them to leave and joins its forks only, so one still delivering a batch (`run_batch` books the box's use
        and its state) when the store closes fails in its thread the same way. Every gym-* thread started since setUp is
        this fixture's pool's, whether or not `manage` still holds its box."""
        for thread in threading.enumerate():
            if thread.name.startswith("gym-") and thread not in self.threads_before:
                thread.join(seconds)

    def script(self, body):
        return {"calls": [("notebook", {"action": "append", "text": "noted"})]} if len(body["input"]) < 6 else {"text": "ok"}

    def swarm(self):
        return Swarm(self.root, settings=self.settings, config={}, store=self.store, router=self.router, pool=self.pool,
                     guard=self.guard, sleep=lambda s: time.sleep(min(s, 0.05)))


class Process(LoopCase):
    def test_the_incubators_reruns_follow_the_tournaments_round_through_the_researcher_under_the_research_guard(self):
        # THE INCUBATOR'S RE-RUNS (Oct 8, 2026, `Swarm.incubator_reruns`): here, not in league/swarm/tournament.py (the
        # owner's deploy), after the round on its thread, through the swarm's own Researcher, only while the guard allows
        # new research (THE GATE'S RESERVE and the brake), and never failing the round.
        from unittest.mock import patch

        from league.swarm import incubator

        sw = self.swarm()
        calls = []

        def reruns(store, settings, researcher, root, *, clock):
            calls.append((store, researcher, Path(root)))
            return {"owed": 1, "queued": ["a@1"], "waiting": [], "spent": []}

        with patch.object(incubator, "reruns", side_effect=reruns):
            self.assertEqual(sw.incubator_reruns()["queued"], ["a@1"])
            self.assertEqual(calls, [(sw.store, sw.researcher, self.root)])
            self.guard.research_held = True
            self.assertIn("held", sw.incubator_reruns())
            self.guard.research_held, self.guard.braked = False, True
            self.assertIn("held", sw.incubator_reruns())
            self.guard.braked = False
            self.assertEqual(len(calls), 1, "held: not asked")
            with patch.object(sw.tournament, "run", return_value={"board": []}):
                self.assertEqual(sw.tournament_round(), {"board": []}, "the round's own row, as before")
            self.assertEqual(len(calls), 2, "after the round")
            with patch.object(sw.tournament, "run", side_effect=RuntimeError("the round failed")):
                with self.assertRaises(RuntimeError):
                    sw.tournament_round()
            self.assertEqual(len(calls), 3, "a round that failed still leaves the cohorts' runs owed: asked all the same")
        with patch.object(incubator, "reruns", side_effect=RuntimeError("boom")):
            self.assertEqual(sw.incubator_reruns(), {"error": "RuntimeError"}, "an error never fails the round")
        errors = [e for e in self.store.events_after(0) if e["payload"].get("action") == "incubator_reruns_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(sw.incubator_reruns(), {}, "nothing owed: no practice record")

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
        m.join(30)  # its pass in flight writes to the store too: it ends before the fixture closes it
        self.assertEqual(len(results), 48)
        errors = {k: v.get("error") for k, v in results.items() if v.get("error")}
        self.assertEqual(errors, {})
        self.assertTrue(all(v.get("starter") for v in results.values()))
        self.assertLess(max(v["seconds"] for v in results.values()), 180)
        self.assertLess(elapsed, 60)
        research = self.store._one("SELECT COALESCE(SUM(trials), 0) AS n FROM runs WHERE purpose='train'")["n"]
        self.assertEqual(research, 48, "one run a family; robustness runs of new bests fill the idle boxes besides")
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

    def test_at_the_gates_reserve_new_research_stops_and_the_gates_rounds_go_on(self):
        """THE GATE NEVER WAITS FOR MIDNIGHT: with the day's Sail research at its line (the guard's hold, no brake), the
        tournament's validation round, the gate round and the nightly forward still start; the architect, a reseed, the
        diagnostician and the researchers' cycles do not, and the Gym is not scaled to zero."""
        self.settings["population"]["reseed_max"] = 4
        (self.root / "swarm.json").write_text(json.dumps({"enabled": True, "gym": self.settings["gym"],
                                                          "researcher": {"idle_seconds": 0}, "population": {"reseed_max": 4}}))
        sw = self.swarm()
        sw.seed()
        for fam in self.store.families(alive=True)[:40]:  # 8 alive: under the start, so the architect would refill
            self.store.retire(fam["id"], "test")
        ran: list[str] = []
        sw.gate.forward_due = lambda: True
        sw.gate.forward = lambda: ran.append("forward") or {"ran": True}
        sw.architect_pass = lambda: ran.append("architect") or {}
        sw.reseed = lambda: ran.append("reseed") or []
        sw.diagnostician.due = lambda: True
        sw.diagnostician.run = lambda: ran.append("diagnostician") or {}
        scaled: list[str] = []
        self.pool.scale_to_zero = lambda why, **kw: scaled.append(why)
        self.store.put("tournament_at", 0.0)
        self.store.put("architect_at", 0.0)
        self.guard.research_held = True
        self.guard.held = "today's Sail research is at its line (13.50 of 15.00)"
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertEqual(set(sw.rounds), {"tournament", "gate", "forward"}, "those three go on to the day's cap")
        self.assertEqual(ran, ["forward"], "no architect pass, no reseed, no diagnostician")
        self.assertEqual(scaled, [], "a hold is no brake: validation and the look need the Gym")
        self.assertIn("research", self.guard.asked, "the births ask for research")
        self.assertFalse(json.loads((self.root / "swarm.heartbeat").read_text())["status"]["braked"], "the heartbeat says no brake")
        # The hold over (a new day, or a raise): the same pass starts the architect again.
        sw.stop.clear()
        self.guard.research_held = False
        self.store.put("architect_at", 0.0)
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertIn("architect", sw.rounds)
        self.assertEqual(ran.count("architect"), 1)
        # And under the brake nothing starts, the gate's rounds included (a low or unreadable balance, the cap itself).
        sw.rounds.clear()
        ran.clear()
        self.store.put("tournament_at", 0.0)
        self.guard.braked = True
        sw.step()
        self.assertEqual((sw.rounds, ran), ({}, []))
        self.assertEqual(len(scaled), 1, "and the brake scales the Gym to zero, as ever")

    def worker_cycles(self, sw, seconds=0.4):
        """The families one researcher worker starts a cycle on in `seconds` (the cycle itself stubbed: what is judged is
        whether the worker starts one), and what it asked the guard for."""
        cycles: list[str] = []
        sw.researcher.cycle = lambda fid: cycles.append(fid) or {}
        self.guard.asked.clear()
        sw.stop.clear()
        worker = threading.Thread(target=sw._worker, args=(0,), daemon=True)
        worker.start()
        time.sleep(seconds)
        sw.stop.set()
        worker.join(10)
        self.assertFalse(worker.is_alive(), "the worker left when asked")
        return cycles, set(self.guard.asked)

    def test_at_the_gates_reserve_a_researcher_starts_no_cycle(self):
        """A researcher's cycle is new research (most of the day's Sail spend): under the guard's hold the worker starts
        none, and with the hold over the same worker takes a family (the control: the hold alone was what stopped it)."""
        sw = self.swarm()
        sw.seed()
        self.guard.research_held = True
        cycles, asked = self.worker_cycles(sw)
        self.assertEqual((cycles, asked), ([], {"research"}), "held: no cycle, and the worker asks for research by name")
        self.guard.research_held = False
        cycles, asked = self.worker_cycles(sw)
        self.assertTrue(cycles, "not held: the worker takes a family")
        self.assertEqual(asked, {"research"})
        self.guard.braked = True
        self.assertEqual(self.worker_cycles(sw)[0], [], "and under the brake none, as ever")

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

    def test_a_retained_openai_hold_does_not_stall_the_separately_funded_sail_pace(self):
        self.settings["researcher"].update(usd_per_hour=2.25, sail_usd_per_hour=2.25)
        self.store.add_spend("openai", 2.0, detail={"role": "architect", "hold": "synthetic-unresolved-request"})
        self.store.add_spend("sail_model", 1.02)
        sw = self.swarm()
        clock = [time.time()]
        sw.clock = lambda: clock[0]
        self.assertFalse(sw.over_pace())
        pace = sw.status()["researcher_pace"]
        self.assertEqual((pace["scope"], pace["limit_usd_per_hour"], pace["spent_last_hour_usd"]),
                         ("sail_model", 2.25, 1.02))
        self.assertIsNone(pace["reason"])
        self.assertEqual(self.store.spent(["openai"]), 2.0, "the unresolved hold still counts against OpenAI's own cap")
        self.store.add_spend("sail_model", 1.23)
        clock[0] += 11
        self.assertTrue(sw.over_pace(), "Sail still stops at its funded rate")
        self.assertIn("Sail models spent", sw.status()["researcher_pace"]["reason"])

    def test_absent_and_null_sail_limit_keep_the_legacy_combined_pace(self):
        self.settings["researcher"]["usd_per_hour"] = 2.25
        self.store.add_spend("sail_model", 1.02)
        self.store.add_spend("openai", 2.0, detail={"hold": "synthetic-unresolved-request"})
        sw = self.swarm()
        for explicit_null in (False, True):
            with self.subTest(explicit_null=explicit_null):
                if explicit_null:
                    self.settings["researcher"]["sail_usd_per_hour"] = None
                else:
                    self.settings["researcher"].pop("sail_usd_per_hour", None)
                self.assertTrue(sw.over_pace())
                pace = sw.status()["researcher_pace"]
                self.assertEqual((pace["scope"], pace["spent_last_hour_usd"]), ("all_models", 3.02))
                self.assertIn("Sail and OpenAI", pace["reason"])

    def test_changing_pace_scope_takes_effect_even_during_the_spend_cache(self):
        self.settings["researcher"]["usd_per_hour"] = 1.0
        self.store.add_spend("sail_model", 0.4)
        self.store.add_spend("openai", 1.0)
        sw = self.swarm()
        self.assertTrue(sw.over_pace())
        self.settings["researcher"]["sail_usd_per_hour"] = 1.0
        self.assertFalse(sw.over_pace())
        self.settings["researcher"]["sail_usd_per_hour"] = None
        self.assertTrue(sw.over_pace())

    def test_invalid_nonfinite_and_negative_pace_limits_pause_research_and_explain_why(self):
        sw = self.swarm()
        for key in ("sail_usd_per_hour", "usd_per_hour"):
            for limit in ("bad", float("nan"), float("inf"), -1, True):
                with self.subTest(key=key, limit=limit):
                    self.settings["researcher"]["sail_usd_per_hour"] = None
                    self.settings["researcher"][key] = limit
                    self.assertTrue(sw.over_pace())
                    pace = sw.status()["researcher_pace"]
                    self.assertIsNone(pace["limit_usd_per_hour"])
                    self.assertIn(f"invalid researcher.{key}", pace["reason"])

    def test_the_architect_grows_the_population_only_under_the_pace_but_always_refills_it(self):
        # THE BUDGET holds population.start to its ceiling (league/ops/budget.py): at the owner's ceiling of $25 a day
        # that is 25 families, so the 48 founders are over the start and the refill is judged under it.
        from league.ops import budget as B

        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "at": time.time(), "meters": {
            "sail": {"research_usd_day": B.ceiling_usd_day("sail")}, "claude": {"research_usd_day": B.ceiling_usd_day("claude")}}}))
        sw = self.swarm()
        sw.seed()
        self.store.add_spend("sail_model", float(self.settings["researcher"]["usd_per_hour"]) + 0.5)  # the hour's spend is past the pace
        self.store.put("tournament_at", time.time())
        self.store.put("architect_at", 0.0)
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertEqual((sw.settings["population"]["ceiling"], sw.settings["population"]["start"]), (25, 25))
        self.assertNotIn("architect", sw.rounds, "48 alive: no growth while the money is spent")
        for fam in self.store.families(alive=True)[:28]:
            self.store.retire(fam["id"], "test")
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertIn("architect", sw.rounds, "20 alive under the start of 25: it refills whatever the pace")

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
        self.assertEqual(kinds, ["train_objective", "started", "stopped"], "the objective's migration runs once, at the start")
        self.assertEqual(sw.run(once=True), 0)
        kinds = [e["payload"].get("action") for e in self.store.events_after(0) if e["kind"] == "swarm.status"]
        self.assertEqual(kinds.count("train_objective"), 1)


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


class Library(LoopCase):
    """THE LIBRARY's wiring (Sept 29, 2026): one Library for the process, handed to the researcher; off without a gateway
    token; in the heartbeat; the pass's block from the seed searches until the strategist names its own."""

    def test_the_swarm_builds_the_library_and_hands_it_to_the_researcher(self):
        from league.swarm import library as L
        from league.tests.test_swarm_library import FakeClient

        sw = self.swarm()
        self.assertIsInstance(sw.library, L.Library)
        self.assertIs(sw.researcher.library, sw.library)
        self.assertFalse(sw.library.enabled(), "off by default")
        self.assertEqual(sw.status()["library"], {"enabled": False})
        client = FakeClient()
        sw = Swarm(self.root, settings=self.settings, config={}, store=self.store, router=self.router, pool=self.pool, guard=self.guard,
                   library=L.Library(self.store, client, self.settings))
        self.assertIsNone(Swarm.library_block(sw), "not switched on: no retrieval")
        self.settings["research"]["enabled"] = True
        block = Swarm.library_block(sw)
        self.assertEqual(block.queries, tuple(self.settings["research"]["seed_queries"][:4]))
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(sw.status()["library"], {"enabled": True, "calls_today": 4, "line": 300, "families_today": 0})


class Heartbeat(LoopCase):
    def test_the_heartbeat_names_the_families_in_a_cycle_now(self):
        sw = self.swarm()
        sw.scheduler.running.update({"fam-b", "fam-a"})
        status = sw.status()
        self.assertEqual((status["running"], status["running_families"]), (2, ["fam-a", "fam-b"]))


if __name__ == "__main__":
    unittest.main()

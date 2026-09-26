"""The House's side of the swarm (league/swarm/hook.py, bands.py, sitefeed.py) and the options House with the swarm
enabled (league/service.py): no agent of its own, no old research, the swarm's step in the tick."""

from __future__ import annotations

import json
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from league import publish
from league.ledger import KINDS, Ledger
from league.swarm import bands, sitefeed
from league.swarm.hook import SwarmStep
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, result
from league.tests.test_options_house import BuildCase

SPEC = {"id": "condor-vrp", "mechanism": "Index options price more movement than follows: sell an iron condor.",
        "structure": "iron_condor", "roots": ["SPY"], "dte": [0, 2]}
ON = {"swarm": {"enabled": True}}


class Proc:
    def __init__(self, pid):
        self.pid = pid
        self.code = None

    def poll(self):
        return self.code


class HookCase(unittest.TestCase):
    """A fake process table: `self.procs[pid] = (cmdline, start)`; `hold(pid)` takes the swarm's lock as that process
    would (a real flock on the lock file, from another open file description), `let_go()` drops it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "state"
        self.root.mkdir()
        self.clock = Clock()
        self.signals: list[tuple[int, int]] = []
        self.spawned: list[Proc] = []
        self.procs: dict[int, tuple[str, str]] = {}
        self.held = None
        self.addCleanup(self.let_go)

    def swarm_cmd(self):
        return f"/usr/bin/python3 -m league.swarm run --root {self.root}"

    def kill(self, pid, sig):
        if pid not in self.procs:
            raise ProcessLookupError(pid)
        if sig:
            self.signals.append((pid, sig))
            if sig == signal.SIGKILL:
                self.procs.pop(pid, None)
                self.let_go()

    def spawn(self):
        proc = Proc(1000 + len(self.spawned))
        self.procs[proc.pid] = (self.swarm_cmd(), f"t{proc.pid}")
        self.spawned.append(proc)
        return proc

    def hold(self, pid, *, start=None, release="/rel/A"):
        import fcntl

        self.let_go()
        self.held = open(self.root / "swarm.lock", "a+")
        fcntl.flock(self.held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.procs.setdefault(pid, (self.swarm_cmd(), start or f"t{pid}"))
        (self.root / "swarm.lock").write_text(json.dumps({"pid": pid, "start": start or self.procs[pid][1], "release": release}))

    def let_go(self):
        if self.held is not None:
            self.held.close()
            self.held = None

    def step(self, config=ON):
        return SwarmStep(self.root, config=config, clock=self.clock, spawn=self.spawn, kill=self.kill, code_dir=Path("/rel/A"),
                         proc=lambda pid: self.procs.get(pid))

    def beat(self, pid, *, at=None, release="/rel/A", started=None):
        (self.root / "swarm.heartbeat").write_text(json.dumps({"pid": pid, "at": self.clock() if at is None else at, "release": release,
                                                              "started_at": started if started is not None else self.clock() - 3600}))


class Supervise(HookCase):
    def test_it_starts_the_swarm_once_and_leaves_a_healthy_one_alone(self):
        step = self.step()
        self.assertEqual(step.supervise()["action"], "started")
        self.hold(1000)
        self.beat(1000)
        self.clock.advance(20)
        self.assertNotIn("action", step.supervise())
        self.assertEqual(len(self.spawned), 1)

    def test_a_live_child_that_has_not_yet_beaten_or_locked_is_running(self):
        step = self.step()
        self.beat(77, at=self.clock() - 3600)  # an old swarm's last heartbeat, its pid dead
        step.supervise()
        for _ in range(4):
            self.clock.advance(31)
            out = step.supervise()
            self.assertNotEqual(out.get("action"), "started", out)
        self.assertEqual(len(self.spawned), 1, "never a second swarm while the first lives")

    def test_disabled_or_stopped_it_starts_nothing(self):
        self.assertEqual(self.step(config={"swarm": {"enabled": False}}).supervise()["idle"], "disabled")
        (self.root / "swarm.stop").write_text("x")
        self.assertIn("swarm.stop", self.step().supervise()["idle"])
        self.assertEqual(self.spawned, [])

    def test_a_house_not_open_for_business_starts_no_swarm_but_leaves_one_running(self):
        step = self.step()
        self.assertEqual(step.supervise(may_start=False)["idle"], "the House is not open for business")
        self.assertEqual(self.spawned, [])
        self.hold(1000)
        self.beat(1000)
        self.assertNotIn("idle", step.supervise(may_start=False))
        self.assertEqual(self.signals, [])

    def test_a_stale_heartbeat_is_a_hang_it_terminates_then_kills_then_restarts(self):
        step = self.step()
        step.supervise()
        self.hold(1000)
        self.beat(1000)
        self.clock.advance(300)
        self.assertIn("stale", step.supervise()["action"])
        self.assertEqual(self.signals, [(1000, signal.SIGTERM)])
        self.clock.advance(31)
        self.assertEqual(step.supervise()["action"], "terminating")
        self.assertEqual(self.signals[-1], (1000, signal.SIGKILL))
        self.spawned[0].code = -9
        self.clock.advance(60)
        self.assertEqual(step.supervise()["action"], "started")

    def test_a_swarm_on_another_release_is_restarted(self):
        self.hold(77, release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        out = self.step().supervise()
        self.assertIn("another release", out["action"])
        self.assertEqual(self.signals, [(77, signal.SIGTERM)])

    def test_it_never_signals_a_pid_that_is_not_the_swarm(self):
        self.hold(77, release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        self.procs[77] = ("/usr/bin/python3 -m league run --root /workspace/state", "t77")  # the pid now belongs to the House
        out = self.step().supervise()
        self.assertEqual(self.signals, [])
        self.assertIn("cannot verify", out["action"])

    def test_it_never_signals_a_reused_pid(self):
        self.hold(77, start="t-old", release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        self.procs[77] = (self.swarm_cmd(), "t-new")  # same number, another process start
        self.step().supervise()
        self.assertEqual(self.signals, [])

    def test_it_never_signals_itself(self):
        import os

        self.hold(os.getpid(), release="/rel/OLD")
        self.beat(os.getpid(), release="/rel/OLD")
        self.step().supervise()
        self.assertEqual(self.signals, [])

    def test_a_start_that_dies_before_it_locks_backs_off(self):
        step = self.step()
        step.supervise()
        self.spawned[-1].code = 1
        self.clock.advance(31)
        self.assertEqual(step.supervise()["action"], "started")
        self.spawned[-1].code = 1
        self.clock.advance(31)
        self.assertIn("waiting", step.supervise()["action"])

    def test_the_log_is_rotated_at_a_start(self):
        from league.swarm.hook import rotate_log

        log = self.root / "swarm.log"
        log.write_bytes(b"x" * 1000)
        rotate_log(log, max_bytes=500)
        self.assertEqual((log.exists(), (self.root / "swarm.log.1").stat().st_size), (False, 1000))

    def test_a_tick_never_raises_into_the_house(self):
        class BrokenLedger:
            def append_many(self, rows):
                raise RuntimeError("disk full")

        store = SwarmStore(self.root)
        store.event("swarm.status", None, {"x": 1})
        store.close()

        class House:
            ledger = BrokenLedger()

        out = self.step().tick(House(), open_for_business=True)
        self.assertIn("mirror_error", out)


class Mirror(HookCase):
    def test_events_reach_the_ledger_once_with_swarm_kinds_and_public_flags(self):
        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
        store.event("swarm.cycle", fam["id"], {"cycle": 1})
        store.event("swarm.pool", None, {"action": "box_ready"})
        store.set_band(fam["id"], "candidate", reason="passed its holdout look")
        store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        step = self.step()
        self.assertEqual(step.mirror(ledger), 5)
        self.assertEqual(step.mirror(ledger), 0)
        rows = list(ledger.iter())
        self.assertEqual([r.kind for r in rows], ["swarm.born", "swarm.band", "swarm.note"], "cycles and pool rows stay in the swarm's table")
        self.assertEqual([r.public for r in rows], [True, True, True])
        self.assertTrue(all(r.agent == "condor-vrp" for r in rows))
        (self.root / "swarm-mirror.json").unlink()
        self.assertEqual(step.mirror(ledger), 5, "a lost cursor re-mirrors idempotently")
        self.assertEqual(len(list(ledger.iter())), 3)
        store.close()
        # The tape: a note is the agent's note, a birth and a band move are the swarm's news.
        events = [e for r in rows for e in publish.to_events(r)]
        self.assertEqual([e["kind"] for e in events], ["swarm.news", "swarm.news", "agent.note"])
        self.assertIn("moves from Gym to Candidate", events[1]["payload"]["text"])

    def test_the_swarm_never_writes_the_houses_own_kinds(self):
        for kind in ("swarm.born", "swarm.retired", "swarm.band", "swarm.note", "swarm.cycle", "swarm.tournament", "swarm.gate",
                     "swarm.architect", "swarm.guard", "swarm.pool", "swarm.status"):
            self.assertIn(kind, KINDS)
        source = "\n".join(p.read_text() for p in (Path(__file__).resolve().parents[1] / "swarm").glob("*.py"))
        for kind in ("agent.born", "agent.died", "agent.thought", "eval.verdict"):
            self.assertNotIn(f'"{kind}"', source)


class Reads(HookCase):
    def test_bands_read_rows_for_the_live_path(self):
        store = SwarmStore(self.root, clock=self.clock)
        a = store.add_family(SPEC, origin="seed")
        b = store.add_family({**SPEC, "id": "tuition"}, origin="seed")
        c = store.add_family({**SPEC, "id": "plain"}, origin="seed")
        for fam in (a, b, c):
            store.add_version(fam["id"], f"# {fam['id']}\nNEEDS = {{}}\n", {"k": 1}, author="seed")
        store.set_state(a["id"], banded_version=1, validation_version=1, validation_line={"passed": True}, typical_max_loss_usd=60.0)
        store.set_band(a["id"], "candidate", reason="passed")
        from league.swarm.gate import run_sha

        store.set_state(b["id"], validation_version=1, validation_line={"passed": True}, typical_max_loss_usd=45.0,
                        review={"sha": run_sha(store.version(b["id"], 1)), "verdict": "pass"})
        store.close()
        rows = {r["family"]: r for r in bands.read(self.root)}
        self.assertEqual(set(rows), {"condor-vrp", "tuition"})
        self.assertEqual((rows["condor-vrp"]["holdout_passed"], rows["condor-vrp"]["validation_passed"], rows["condor-vrp"]["band"]),
                         (True, True, "candidate"))
        self.assertEqual((rows["tuition"]["holdout_passed"], rows["tuition"]["validation_passed"]), (False, True))
        self.assertEqual(set(rows["tuition"]), {"family", "band", "structure", "roots", "holdout_passed", "validation_passed", "version",
                                                "code", "params", "run_sha", "typical_max_loss_usd", "seed_era", "forward"})
        self.assertIn("# tuition", rows["tuition"]["code"])
        self.assertEqual((rows["tuition"]["typical_max_loss_usd"], rows["tuition"]["seed_era"]), (45.0, True))

    def test_tuition_rows_are_only_reviewed_and_not_yet_failed_versions(self):
        from league.swarm.gate import run_sha

        store = SwarmStore(self.root, clock=self.clock)
        cases = {}
        for fid in ("unreviewed", "reviewed", "refused", "looked-failed", "demoted"):
            fam = store.add_family({**SPEC, "id": fid}, origin="seed")
            v = store.add_version(fam["id"], f"# {fid}\nNEEDS = {{}}\n", {}, author="seed")
            store.set_state(fid, validation_version=v["n"], validation_line={"passed": True})
            cases[fid] = run_sha(v)
        store.set_state("reviewed", review={"sha": cases["reviewed"], "verdict": "pass"})
        store.set_state("refused", review={"sha": cases["refused"], "verdict": "fail"}, gate_outcome={"sha": cases["refused"], "result": "refused"})
        store.set_state("looked-failed", review={"sha": cases["looked-failed"], "verdict": "pass"},
                        gate_outcome={"sha": cases["looked-failed"], "result": "failed"})
        store.set_state("demoted", review={"sha": cases["demoted"], "verdict": "pass"},
                        gate_outcome={"sha": cases["demoted"], "result": "demoted"})
        store.close()
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["reviewed"])

    def test_bands_read_never_raises(self):
        self.assertEqual(bands.read(self.root / "nowhere"), [])
        (self.root / "swarm.sqlite").write_text("not a database")
        self.assertEqual(bands.read(self.root), [])

    def test_site_inputs_are_counts_and_words_never_programs_or_results(self):
        store = SwarmStore(self.root, clock=self.clock)
        fam = store.add_family(SPEC, origin="seed")
        store.add_version(fam["id"], "SECRET_PROGRAM = 1\n", {}, author="seed")
        store.add_run(fam["id"], 1, result("x"), window="train", stress=1.0, purpose="train", program_years=2.5)
        store.add_spend("sail_model", 1.25)
        store.add_forward(fam["id"], "shadow", [{"id": "t1", "day": "d", "pnl": 3.0, "max_loss": 50.0}])
        dead = store.add_family({**SPEC, "id": "gone"}, origin="seed")
        store.retire(dead["id"], "no improvement")
        store.close()
        out = sitefeed.site_inputs(self.root)
        self.assertEqual(out["gym"]["trials"], 1)
        self.assertEqual(out["gym"]["market_years"], 2.5)
        self.assertEqual((out["gym"]["families_alive"], out["gym"]["families_retired"]), (1, 1))
        self.assertEqual(out["compute"]["sail_usd"], 1.25)
        agent = next(a for a in out["agents"] if a["id"] == "condor-vrp")
        self.assertEqual(agent["record"]["forward"], {"trades": 1, "wins": 1, "pnl_usd": 3.0})
        self.assertNotIn("SECRET_PROGRAM", json.dumps(out))
        checkpoint = publish.build_checkpoint({**out, "started_at": None}, "2026-09-26T12:00:00Z")
        self.assertEqual({a["id"] for a in checkpoint["agents"]}, {"condor-vrp", "gone"})
        self.assertEqual(checkpoint["gym"]["trials"], 1)


class SwarmHouse(BuildCase):
    def build_on(self, **kw):
        spawned = []

        def fake_popen(self_step):
            spawned.append(1)
            return Proc(4242)

        with patch("league.swarm.hook.SwarmStep._popen", fake_popen):
            house = self.build(config=ON, research=True, merton=True, **kw)
        return house, spawned

    def test_the_swarms_house_builds_no_old_research_merton_or_births(self):
        house, _ = self.build_on()
        self.assertIsInstance(house.swarm, SwarmStep)
        self.assertIsNone(house.researcher)
        self.assertIsNone(house.merton)
        self.assertIsNone(getattr(house, "budget", None))
        self.assertFalse(house.settings.births)
        self.assertNotIn("site_inputs", vars(house), "the House's own site_inputs reads house.swarm")

    def test_an_empty_root_tick_seats_no_agent_and_spends_no_research(self):
        house, _ = self.build_on()
        calls = []
        house.swarm.spawn = lambda: calls.append(1) or Proc(4343)
        house.swarm.kill = lambda pid, sig: None
        summary = house.tick()
        house.wait(60)
        self.assertEqual([e for e in house.ledger.iter(kinds="agent.born")], [])
        self.assertEqual(len(house.registry.agents), 0)
        self.assertFalse((Path(self.dir.name) / "state" / "provider.sqlite").exists(), "no old provider, no research spend")
        self.assertEqual([e for e in house.ledger.iter(kinds="provider.request")], [])
        self.assertEqual(summary["swarm"]["process"]["action"], "started")
        self.assertEqual(calls, [1])

    def test_the_state_roots_swarm_json_switches_it_on_without_a_deploy(self):
        root = Path(self.dir.name) / "state"
        root.mkdir(parents=True, exist_ok=True)
        (root / "swarm.json").write_text(json.dumps({"enabled": True}))
        house = self.build(config={"swarm": {"enabled": False}})
        self.assertIsInstance(house.swarm, SwarmStep)
        self.assertFalse(house.settings.births)

    def test_a_canary_never_runs_the_swarm(self):
        with patch("league.swarm.hook.SwarmStep._popen", side_effect=AssertionError("no swarm in a canary")):
            house = self.build(config=ON, canary=True)
        self.assertIsNone(house.swarm)


if __name__ == "__main__":
    unittest.main()

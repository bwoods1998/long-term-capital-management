"""The tick never blocks on background work (Sept 23, 2026).

At 05:07Z a hypothesis replay held the House's probe box through a Sail call that hung for about
seven minutes (`replay:hypothesis:pending failed (SandboxError: house-probe: SailboxError: sailbox
transport ...)`), and the House's first tick, which wanted the same box for a birth, waited about
twelve. A hung first tick also held the House's exit on TERM, and the watchdog rolled the release
back. These tests run the House on the real `SailSandbox` over a fake Sail client that stalls the
way that transport did, and check that the tick completes in bounded time, health stays fresh, the
work the tick wanted is deferred with its reason, and nothing is charged to any strategy.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import runner
from league.agents import code_sha
from league.house import PROBE_BOX, Settings
from league.replay import run_replay
from league.sandbox import SailSandbox, SandboxBusy, SandboxError
from league.tests.test_house import BUYER, HouseCase
from league.tests.test_hypotheses import FoundryCase

#: A tick that waits on nothing takes well under a second here; the stall it must not wait for
#: lasts until the test releases it (30 s at most).
BOUNDED = 8.0


class Transport(RuntimeError):
    """What `ltcm.sailbox` raises when its HTTPS call times out."""


class StallingSail:
    """The part of `ltcm.sailbox.SailboxClient` that `SailSandbox` uses. `exec` answers by running
    the real runner (or replay) in this process; for an agent in `stalled` it first blocks, as the
    Sept 23 transport did, until `release` is set, and then fails as that transport failed."""

    def __init__(self):
        self.boxes: dict[str, dict] = {}
        self.stalled: set[str] = set()
        self.stall_checkpoints = False  # a parent's checkpoint hangs, then fails, like `exec` above
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list[tuple] = []
        self.observer = None  # called with each method's name as it is entered
        self._n = 0
        self._lock = threading.Lock()

    def agent_of(self, box: str) -> str:
        return self.boxes[box]["name"].split("-", 1)[1]

    def _seen(self, name: str) -> None:
        if self.observer is not None:
            self.observer(name)

    def from_checkpoint(self, checkpoint, *, name, timeout=None):
        self._seen("from_checkpoint")
        self.calls.append(("from_checkpoint", checkpoint, timeout))
        with self._lock:
            self._n += 1
            box = f"sb_{self._n:04d}"
            self.boxes[box] = {"status": "running", "files": {}, "name": name}
        return {"sailbox_id": box, "checkpoint_id": checkpoint, "status": "running"}

    def set_egress(self, box, hosts):
        self._seen("set_egress")
        return {}

    def get(self, box):
        self._seen("get")
        return {"sailbox_id": box, "status": self.boxes[box]["status"]}

    def resume(self, box, *, timeout=None):
        self._seen("resume")
        self.calls.append(("resume", box, timeout))
        self.boxes[box]["status"] = "running"
        return {}

    def upload(self, box, path, content, *, mode=0o600, timeout=None):
        self._seen("upload")
        self.calls.append(("upload", box, path, timeout))
        self.boxes[box]["files"][path] = bytes(content)
        return {}

    def exec(self, box, argv, *, timeout=600):
        self._seen("exec")
        agent = self.agent_of(box)
        if agent in self.stalled:
            self.entered.set()
            self.release.wait(30)
            raise Transport("sailbox transport failed: TimeoutError")
        command = argv[-1]
        cwd = command.split(" && ", 1)[0].removeprefix("cd ").strip()
        spec = json.loads(self.boxes[box]["files"][f"{cwd}/spec.json"].decode("utf-8"))
        if "replay.py" in command:
            result, marker = run_replay(spec["code"], spec["params"], spec["tape"], stake=spec["stake"], limits=spec["limits"]), "REPLAY-RESULT"
        elif spec.get("mode") == "needs":
            result, marker = runner.needs_of(spec["code"]), runner.MARKER
        else:
            result, marker = runner.decide(spec["code"], json.loads(json.dumps(spec["ctx"]))), runner.MARKER
        return SimpleNamespace(stdout=f"\n{marker} {spec['token']} {json.dumps(result)}\n", stderr="", return_code=0)

    def sleep(self, box):
        self._seen("sleep")
        self.calls.append(("sleep", box))
        self.boxes[box]["status"] = "sleeping"
        return {}

    def checkpoint(self, box, *, name=None, ttl_seconds=None, timeout=None):
        self._seen("checkpoint")
        self.calls.append(("checkpoint", box, timeout))
        if self.stall_checkpoints:
            self.entered.set()
            self.release.wait(30)
            raise Transport("sailbox transport failed: TimeoutError")
        return {"checkpoint_id": f"cp_{box}", "sailbox_id": box}

    def terminate(self, box):
        self._seen("terminate")
        self.boxes[box]["status"] = "terminated"
        return {}


class StalledSailCase(HouseCase):
    def setUp(self):
        self.sail = StallingSail()
        self.closed = False
        super().setUp()

    def tearDown(self):
        self.sail.release.set()  # never leave a stalled thread behind, or wait for one
        if not self.closed:
            self.house.close(wait=None)
        self.dir.cleanup()

    def new_house(self, **kw):
        from league.economy import load_game
        from league.house import House
        from league.tests.fakes import FakeBroker

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        kw.setdefault("game", game)
        self.sandbox = SailSandbox(self.sail, Path(self.dir.name) / "sandbox.json", image_checkpoint="cp_image", background_sleep=True)
        return House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker, "alpaca": FakeBroker("alpaca", cash="500")},
            sandbox=self.sandbox, alpaca_data=self.data, clock=self.clock,
            settings=Settings(mark_every_seconds=0, research=False, box_wait_seconds=0.2, probe_wait_seconds=0.5), **kw,
        )

    def stall_in_background(self, agent: str, key: str, work) -> None:
        """A background job that enters `agent`'s box and hangs there, as at 05:07Z."""
        self.sail.stalled.add(agent)
        self.assertTrue(self.house._background(key, work))
        self.assertTrue(self.sail.entered.wait(5), "the background job never reached the box")

    def timed_tick(self) -> tuple[dict, float]:
        started = time.monotonic()
        summary = self.house.tick()
        return summary, time.monotonic() - started

    def health(self) -> dict:
        return json.loads((Path(self.dir.name) / "house" / "health.json").read_text(encoding="utf-8"))


class TheProbeBox(StalledSailCase):
    def architect(self, name="architect-buyer"):
        return patch("league.strategies.all_strategies", return_value=[
            {"name": name, "family": "architect-test", "code": BUYER, "why": "a merged test strategy"}])

    def test_a_birth_defers_while_background_work_holds_the_probe_box_and_the_tick_completes(self):
        self.stall_in_background(PROBE_BOX, "replay:hypothesis:pending", lambda: self.house.sandbox.needs(PROBE_BOX, BUYER))
        living = len(self.house.registry.living())
        with self.architect():
            summary, seconds = self.timed_tick()
            self.assertLess(seconds, BOUNDED)
            self.assertEqual(len(self.house.registry.living()), living, "no birth while the probe box is held")
            health = self.health()
            self.assertEqual(health["at"], summary["at"])  # the tick finished and said so
            self.assertIn("births", health["deferred"])
            self.assertIn("probe box is in use by background work", health["deferred"]["births"]["reason"])
            told = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert")]
            self.assertTrue(any(t.startswith("births deferred to a later tick") for t in told), told)
            # A second tick while it is still held: still bounded, told once, counted twice.
            summary, seconds = self.timed_tick()
            self.assertLess(seconds, BOUNDED)
            self.assertEqual(self.health()["deferred"]["births"]["count"], 2)
            self.assertEqual(sum(t.startswith("births deferred") for t in (e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert"))), 1)
            # The background job fails as it did in production: an alert about infrastructure.
            self.sail.release.set()
            self.house.wait(10)
            self.assertTrue(any("replay:hypothesis:pending failed (SandboxError" in e.payload["text"]
                                for e in self.house.ledger.iter(kinds="ops.alert")))
            self.sail.stalled.clear()
            self.timed_tick()
        born = [a for a in self.house.registry.living() if a.founder == "architect-buyer"]
        self.assertEqual(len(born), 1, "born on the first tick after the probe box is free")
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)  # nothing was ever a trial

    def test_the_tick_does_not_wait_when_the_probe_box_is_free(self):
        with self.architect():
            summary, seconds = self.timed_tick()
        self.assertLess(seconds, BOUNDED)
        self.assertEqual([a.founder for a in self.house.registry.living()], ["architect-buyer"])
        self.assertEqual(self.health()["deferred"], {})

    def test_a_research_admission_never_waits_for_the_probe_box_under_the_lifecycle_lock(self):
        from league.admissions import Admissions

        parent = self.seated()
        with self.house._lifecycle_lock:
            generation = self.house._generation(parent.id)
        needs = self.house.registry.get(parent.id).needs
        candidate = {"code": BUYER + "\n# a better idea\n", "params": {"notional": 10.0}, "needs": needs, "passed": True,
                     "purpose": "a replay-passing candidate"}
        self.stall_in_background(PROBE_BOX, "replay:hypothesis:pending", lambda: self.house.sandbox.needs(PROBE_BOX, BUYER))
        started = time.monotonic()
        with self.house._lifecycle_lock:
            row = Admissions(self.house.ledger).enqueue(parent.id, generation, candidate, "s-1")
            self.assertIsNone(self.house._admit_candidate(row))
        self.assertLess(time.monotonic() - started, BOUNDED)
        last = Admissions(self.house.ledger).rows()[-1]
        self.assertEqual(last["status"], "deferred")
        self.assertIn("probe box is in use", last["reason"])
        self.assertEqual(len(self.house.registry.living()), 1)  # nothing was born or displaced

    def test_revival_waits_for_the_probe_box_and_is_not_lost(self):
        self.house._state["replay_rules"] = "an older gate"
        revived = []
        self.house._revive_near_misses = lambda **kw: revived.append(True) or []
        self.stall_in_background(PROBE_BOX, "replay:hypothesis:pending", lambda: self.house.sandbox.needs(PROBE_BOX, BUYER))
        _, seconds = self.timed_tick()
        self.assertLess(seconds, BOUNDED)
        self.assertEqual(revived, [])
        self.assertTrue(self.house._state.get("revive_pending"))
        self.sail.release.set()
        self.house.wait(10)
        self.sail.stalled.clear()
        self.timed_tick()
        self.assertEqual(revived, [True])
        self.assertNotIn("revive_pending", self.house._state)
        self.timed_tick()
        self.assertEqual(revived, [True], "once per change of the rules")


class ResearchAdmissions(StalledSailCase):
    """Review of PR 159: a research admission held the lifecycle lock, which every wake needs, through
    the child's NEEDS probe and the parent's box fork (a Sail checkpoint and restore, at the client's
    ten- and fifteen-minute timeouts), so a Sail stall on the research thread stalled the whole tick
    (reproduced: 6.4 s of tick for a 6 s stall of `checkpoint`), and TERM with it."""

    def setUp(self):
        super().setUp()
        self.under_lock: list[str] = []  # Sail calls made while the lifecycle lock was held off the tick's thread
        self.tick_thread = threading.current_thread()
        lock = self.house._lifecycle_lock
        self.sail.observer = lambda name: (self.under_lock.append(name)
                                           if threading.current_thread() is not self.tick_thread and lock._is_owned() else None)
        # The stall is released after the bound, so a regression fails quickly instead of hanging.
        timer = threading.Timer(BOUNDED + 2, self.sail.release.set)
        timer.daemon = True
        timer.start()
        self.addCleanup(timer.cancel)

    def candidate_ready(self):
        parent = self.seated()
        self.timed_tick()  # its box exists, so a fork of it would be a checkpoint and a restore
        self.assertIsNotNone(self.sandbox.box_of(parent.id))
        self.house.record_is_empty = lambda agent: False  # a record to protect: the candidate becomes a child
        code = BUYER + "\n# a better idea\n"
        self.house.researcher = SimpleNamespace(research=lambda *a, **k: SimpleNamespace(
            candidate={"code": code, "needs": parent.needs, "params": parent.params, "purpose": "a replay-passing candidate",
                       "numbers": {}, "passed": True}, consulted=""))
        return parent, code

    def research_in_background(self, parent) -> tuple[threading.Event, list]:
        done, errors = threading.Event(), []

        def run():
            try:
                self.house.research(parent)
            except BaseException as exc:  # noqa: BLE001 - reported by the test
                errors.append(exc)
            finally:
                done.set()

        threading.Thread(target=run, daemon=True).start()
        return done, errors

    def children(self, code):
        return [a for a in self.house.registry.living() if a.code == code]

    def test_a_research_admission_forks_no_box_under_the_lifecycle_lock_and_the_tick_never_waits(self):
        from league.admissions import Admissions

        parent, code = self.candidate_ready()
        self.sail.stall_checkpoints = True  # the parent's checkpoint would hang, as the 05:07Z transport did
        done, errors = self.research_in_background(parent)
        deadline = time.monotonic() + 5
        while not (done.is_set() or self.sail.entered.is_set()) and time.monotonic() < deadline:
            time.sleep(0.01)
        summary, seconds = self.timed_tick()
        self.assertLess(seconds, BOUNDED)
        self.assertEqual(self.health()["at"], summary["at"])
        self.assertTrue(done.wait(BOUNDED), "the research admission hung in Sail")
        self.assertEqual(errors, [])
        self.assertEqual(self.under_lock, [], "a Sail call was made under the lifecycle lock off the tick's thread")
        self.assertFalse(any(c[0] == "checkpoint" for c in self.sail.calls), "no parent's box was checkpointed")
        [child] = self.children(code)
        self.assertEqual(child.parent, parent.id)
        self.assertEqual(self.house.evaluator.rung(child.id), 1)
        forked = self.house.ledger.last("agent.forked", agent=parent.id).payload
        self.assertEqual((forked["child"], forked["box_forked"]), (child.id, False))  # the clean image
        self.assertEqual(Admissions(self.house.ledger).rows()[-1]["status"], "admitted")
        # Its NEEDS probe was read once, before the lock, and charged to the child as at any birth.
        charges = [e.payload for e in self.house.ledger.iter(kinds="credit.charge", agent=child.id)]
        self.assertEqual([c["detail"]["for"] for c in charges if "NEEDS" in c.get("detail", {}).get("for", "")], ["reading its strategy's NEEDS"])
        self.timed_tick()  # the child wakes in a box of its own, from the image
        self.assertIsNotNone(self.sandbox.box_of(child.id))

    def test_a_research_admission_stalled_in_its_needs_probe_holds_nothing_the_tick_needs(self):
        from league.admissions import Admissions

        parent, code = self.candidate_ready()
        self.sail.stalled.add(PROBE_BOX)
        done, errors = self.research_in_background(parent)
        self.assertTrue(self.sail.entered.wait(5), "the admission never reached the probe box")
        self.house._state["next_wake"][parent.id] = self.clock()  # due again
        summary, seconds = self.timed_tick()
        self.assertLess(seconds, BOUNDED)
        self.assertIn(parent.id, summary["woke"])  # its wake did not wait for the research thread
        self.assertEqual(self.health()["at"], summary["at"])
        self.sail.release.set()
        self.assertTrue(done.wait(BOUNDED))
        self.assertEqual(errors, [])
        self.assertEqual(self.under_lock, [])
        self.assertEqual(self.children(code), [])
        [row] = Admissions(self.house.ledger).pending()
        self.assertEqual(row["status"], "deferred")
        self.assertTrue(row["reason"].startswith("infrastructure: SandboxError"), row["reason"])
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)  # Sail's failure is nobody's trial
        # Not lost: the tick's admission pass seats it once Sail answers.
        self.sail.stalled.clear()
        with self.house._lifecycle_lock:
            child = self.house._admit_candidate(row, displace=True)
        self.assertEqual(self.children(code), [child])

    def test_term_while_a_research_admission_hangs_in_sail_still_closes_the_house(self):
        parent, code = self.candidate_ready()
        self.sail.stalled.add(PROBE_BOX)
        self.assertTrue(self.house._background(f"research:{parent.id}", self.house.research, parent))
        self.assertTrue(self.sail.entered.wait(5), "the admission never reached the probe box")
        started = time.monotonic()
        self.house.begin_close()  # what TERM does (league/__main__.py)
        self.house._state["next_wake"][parent.id] = self.clock()
        summary = self.house.tick()  # the tick in hand returns: nothing it needs is held
        self.house.close(wait=1)
        self.assertLess(time.monotonic() - started, BOUNDED)
        self.assertIn(parent.id, summary["woke"])
        self.assertEqual(self.under_lock, [])
        self.closed = True

    def test_a_candidate_the_tick_seats_while_research_probes_it_is_born_once(self):
        from league.admissions import Admissions

        parent, code = self.candidate_ready()
        probe, seated = self.sandbox.needs, []

        def needs(agent, source, **kw):
            run = probe(agent, source, **kw)
            if source == code and not seated:
                seated.append(True)
                # Meanwhile the tick's refill seats the same queued candidate.
                with self.house._lifecycle_lock:
                    [row] = Admissions(self.house.ledger).pending()
                    seated.append(self.house._admit_candidate(row, displace=True))
            return run

        with patch.object(self.sandbox, "needs", side_effect=needs):
            self.house.research(parent)
        self.assertIsNotNone(seated[1])
        self.assertEqual(self.children(code), [seated[1]], "born once")
        self.assertEqual(Admissions(self.house.ledger).rows()[-1]["status"], "admitted")
        # The probe research bought for it seated nobody: it is the parent's, as a validation probe is.
        charges = [e.payload["detail"]["for"] for e in self.house.ledger.iter(kinds="credit.charge", agent=parent.id) if "detail" in e.payload]
        self.assertIn("reading a candidate's NEEDS for an admission that did not seat it", charges)

    def test_a_research_admission_that_must_wait_buys_no_probe(self):
        from league.admissions import Admissions

        parent, code = self.candidate_ready()
        self.house.game["economy"]["max_population"] = 1
        execs = len([c for c in self.sail.calls if c[0] == "upload"])
        self.house.research(parent)
        self.assertIn("population is full", Admissions(self.house.ledger).rows()[-1]["reason"])
        self.assertEqual(len([c for c in self.sail.calls if c[0] == "upload"]), execs, "no probe for an admission that waits")


class AnAgentsBox(StalledSailCase):
    def test_a_wake_whose_box_is_busy_is_skipped_and_retried_on_the_next_tick(self):
        agent = self.seated()
        # Its research replaying a candidate in its own box, hung in Sail.
        self.stall_in_background(agent.id, f"research:{agent.id}", lambda: self.house.sandbox.decide(agent.id, BUYER, {}))
        summary, seconds = self.timed_tick()
        self.assertLess(seconds, BOUNDED)
        self.assertIn(agent.id, summary["woke"])
        self.assertEqual(summary["orders"], 0)
        self.assertIn(agent.id, self.health()["deferred"]["wakes"]["reason"])
        self.assertLessEqual(self.house._state["next_wake"][agent.id], self.clock())  # due again at once
        self.assertFalse(any("its box did not run" in e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert")))
        self.sail.release.set()
        self.house.wait(10)
        self.sail.stalled.clear()
        summary, _ = self.timed_tick()
        self.assertIn(agent.id, summary["woke"])
        self.assertEqual(summary["orders"], 1, "woken normally once its box is free")

    def test_a_replay_box_that_does_not_answer_is_infrastructure_not_a_trial(self):
        agent = self.house.spawn("buyer", "test-family", BUYER, reason="a test agent")
        self.sail.stalled.add(agent.id)
        self.sail.release.set()  # it fails at once, as a timed-out transport does
        out = self.house._replay_own(agent)
        self.assertEqual(out["skipped"], "replay box unavailable (infrastructure)")
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)
        text = self.house.ledger.last("ops.alert").payload["text"]
        self.assertIn("infrastructure and not a trial", text)
        # The words `hypotheses._retire_unrunnable` counts against a line are not in it.
        self.assertIsNone(re.match(r"^([a-z][a-z0-9-]{1,40}): (?:replay could not run|its replay was not run|a candidate's replay was not run) \(", text))
        self.assertNotIn(agent.id, self.house._state["tried"])  # tried again on its next wake


class Shutdown(StalledSailCase):
    def test_term_during_a_hung_background_job_still_closes_the_house_within_its_wait(self):
        agent = self.seated()
        self.house.tick()  # its box exists and was put to sleep once
        self.stall_in_background(PROBE_BOX, "replay:hypothesis:pending", lambda: self.house.sandbox.needs(PROBE_BOX, BUYER))
        # A background sleep queued behind the hung box used to hold the pool, sleep_all and exit.
        self.house.sandbox._sleep(PROBE_BOX)
        started = time.monotonic()
        self.house.begin_close()  # what TERM does (league/__main__.py)
        summary = self.house.tick()  # the tick in hand finishes, skipping births
        self.assertFalse(self.house._background("ops:anything", lambda: None), "no new background work once closing")
        count = self.house.sandbox.sleep_all(seconds=2)
        self.house.close(wait=1)
        self.assertLess(time.monotonic() - started, BOUNDED)
        self.assertEqual(count, 2)  # the probe box and the agent's
        box = self.house.sandbox.box_of(agent.id)
        self.assertEqual(self.sail.boxes[box]["status"], "sleeping")
        self.assertIn("at", summary)
        self.closed = True


class TheSandbox(unittest.TestCase):
    """The try-lock itself, on the sandbox."""

    def setUp(self):
        import tempfile

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.sail = StallingSail()
        self.addCleanup(self.sail.release.set)
        self.box = SailSandbox(self.sail, Path(self.dir.name) / "sandbox.json", image_checkpoint="cp_image")

    def hold(self, agent: str) -> threading.Thread:
        self.sail.stalled.add(agent)
        thread = threading.Thread(target=lambda: self.assertRaises(SandboxError, self.box.needs, agent, BUYER), daemon=True)
        thread.start()
        self.assertTrue(self.sail.entered.wait(5))
        return thread

    def test_patience_refuses_a_busy_box_quickly_and_waiting_is_the_default(self):
        self.hold("alpha")
        self.assertTrue(self.box.busy("alpha"))
        started = time.monotonic()
        with self.box.patience(0.2):
            with self.assertRaises(SandboxBusy):
                self.box.decide("alpha", BUYER, {})
            self.assertTrue(self.box.decide("beta", BUYER, {"now": "n"}).result is not None)  # another box is not held up
        self.assertLess(time.monotonic() - started, BOUNDED)
        self.assertIsNone(getattr(self.box._patience, "seconds", None))  # restored

    def test_a_claim_is_reentrant_for_its_holder_and_refused_to_others(self):
        with self.box.claim(PROBE_BOX, wait=0) as held:
            self.assertTrue(held)
            self.assertTrue(self.box.needs(PROBE_BOX, BUYER).result["ok"])  # the holder runs inside it
            other: list[bool] = []
            thread = threading.Thread(target=lambda: other.append(self.box.claim(PROBE_BOX, wait=0.1).__enter__()))
            thread.start()
            thread.join(5)
            self.assertEqual(other, [False])
        self.assertFalse(self.box.busy(PROBE_BOX))

    def test_sail_calls_carry_tighter_timeouts_than_the_clients_five_minutes(self):
        self.box.needs("alpha", BUYER)
        uploads = [c for c in self.sail.calls if c[0] == "upload"]
        self.assertTrue(uploads)
        self.assertTrue(all(60 <= c[3] < 300 for c in uploads), uploads)
        box = self.box.box_of("alpha")
        self.sail.boxes[box]["status"] = "sleeping"
        self.box.needs("alpha", BUYER)
        resume = [c for c in self.sail.calls if c[0] == "resume"]
        self.assertEqual(resume, [("resume", box, SailSandbox.RESUME_TIMEOUT)])
        self.assertLess(SailSandbox.RESUME_TIMEOUT, 300)

    def test_a_fork_and_a_new_box_carry_tighter_timeouts_than_the_clients_ten_and_fifteen_minutes(self):
        self.box.needs("alpha", BUYER)
        self.assertTrue(self.box.fork("alpha", "beta"))
        box = self.box.box_of("alpha")
        self.assertIn(("checkpoint", box, SailSandbox.CHECKPOINT_TIMEOUT), self.sail.calls)
        restores = [c for c in self.sail.calls if c[0] == "from_checkpoint"]
        self.assertEqual(restores, [("from_checkpoint", "cp_image", SailSandbox.CREATE_TIMEOUT),
                                    ("from_checkpoint", f"cp_{box}", SailSandbox.CREATE_TIMEOUT)])
        self.assertLess(SailSandbox.CHECKPOINT_TIMEOUT, 600)
        self.assertLess(SailSandbox.CREATE_TIMEOUT, 900)

    def test_a_background_sleep_gives_up_on_a_box_a_run_holds(self):
        self.hold("alpha")
        box = self.box.box_of("alpha")
        with patch.object(SailSandbox, "SLEEP_WAIT", 0.1):
            started = time.monotonic()
            self.box._sleep_later("alpha", box)
            self.assertLess(time.monotonic() - started, BOUNDED)
        self.assertNotIn(("sleep", box), self.sail.calls)


class QueuedSleeps(unittest.TestCase):
    def test_one_queued_sleep_a_box_and_none_lost(self):
        import tempfile

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        sail = StallingSail()
        box = SailSandbox(sail, Path(folder.name) / "sandbox.json", image_checkpoint="cp_image", background_sleep=True)
        with box.claim("alpha", wait=0):  # a run in hand: the sleeps queue behind it
            box.needs("alpha", BUYER)
            box._sleep("alpha")
            box._sleep("alpha")
            self.assertEqual(len(box._sleeps_queued), 1)
        box.drain()
        self.assertEqual(sail.calls.count(("sleep", box.box_of("alpha"))), 1)
        box.needs("alpha", BUYER)  # a later run queues its own
        box.drain()
        self.assertEqual(sail.calls.count(("sleep", box.box_of("alpha"))), 2)


class HypothesisCards(FoundryCase):
    def test_a_card_whose_replay_box_does_not_answer_stays_pending_and_is_not_a_trial(self):
        failing = SandboxError("house-probe: Transport: sailbox transport failed: TimeoutError")
        with patch.object(self.house.sandbox, "needs", side_effect=failing):
            self.call()
        pending = {c["name"] for c in self.foundry.pending()}
        self.assertEqual(pending, {"sawtooth", "idle"})  # the unsafe one was refused before any box
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)
        told = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertEqual(sum("its replay did not run, infrastructure" in t for t in told), 1, "the batch stops at the outage")
        # With the box back, the next attempt evaluates them as before.
        self.foundry.evaluate_all([c["id"] for c in self.foundry.pending()])
        outcomes = {c["name"]: self.foundry.evaluations()[c["id"]]["outcome"] for c in self.foundry.cards().values()}
        self.assertEqual(outcomes, {"sawtooth": "passed", "idle": "failed", "unsafe": "invalid"})


if __name__ == "__main__":
    unittest.main()

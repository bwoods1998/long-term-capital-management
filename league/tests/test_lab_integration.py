"""Deploy 3's integration of E3 (the tick never blocks), D-core (the lab box and its batch evaluator)
and D-evo (the Alpha Lab), Sept 23, 2026: the fixes the reviews and the merge asked for.

- A corrupt tape in the lab box reads as missing and is sent again, instead of failing every batch.
- A candidate the box could not start a process for is the box's failure, never the candidate's result.
- A bound lab box that is gone is never replaced by an agent-sized box from the agents' image.
- The lab box is held like any other box: a caller's patience governs it, and its Sail calls carry
  the tighter timeouts.
- The service binds the lab box `league/config.json` names and hands that same evaluator to the lab.
- A lab graduate's birth makes no Sail call under the House's lifecycle lock, and waits (never
  blocks the tick) while the probe box is busy.
- The lab stops while the House is stopped, deploying or below the "all" frontier tier, and opens
  the sealed holdout only through `House._holdout`.
"""

from __future__ import annotations

import ast
import gzip
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from league import lab as lab_module
from league import service
from league.house import PROBE_BOX
from league.lab import Lab, static_literal
from league.labbox import LabBox
from league.replay import NOT_STARTED, _main_batch, load_tape, not_evaluated, run_batch
from league.sandbox import (SEALED, TAPE_DIR, BoundBoxGone, LocalSandbox, SailSandbox, SandboxBusy, SandboxError, tape_bytes,
                            tape_digest)
from league.tests.fakes import FakeBroker
from league.tests.test_house import IDLE
from league.tests.test_lab import DESK, KNOB, FakeBox, FakeModel, LabCase
from league.tests.test_lab_batch import LIMITS, BatchSail, seed_candidates, single, small
from league.tests.test_tick_never_blocks import BOUNDED, StalledSailCase

#: The lab box `league/config.json` names (scripts/lab_box.py created it, Sept 23, 2026).
CONFIG_BOX = service.load_config()["lab"]["box_id"]


def corrupt(raw: bytes) -> bytes:
    """A gzip file whose header is intact and whose deflate stream is not: `zlib.error`, not OSError."""
    return raw[:10] + bytes(b ^ 0xFF for b in raw[10:40]) + raw[40:]


class TimedBatchSail(BatchSail):
    """`BatchSail` that also keeps the timeout each download was given."""

    def download(self, box, path, *, timeout=300.0):
        self.timeouts.append(("download", path, timeout))
        return super().download(box, path, timeout=timeout)


class Tapes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.tape = small("alpaca")
        self.digest = tape_digest(self.tape)
        self.candidates = seed_candidates("alpaca")[:2]

    def tearDown(self):
        self.dir.cleanup()

    def test_a_corrupt_tape_reads_as_missing_so_it_is_sent_again(self):
        path = self.root / "tape.json.gz"
        path.write_bytes(corrupt(gzip.compress(tape_bytes(self.tape), 6, mtime=0)))
        tape, why = load_tape(str(path), self.digest)
        self.assertIsNone(tape)
        self.assertIn("send it again", why)
        summary = _main_batch({"candidates": self.candidates, "tape_path": str(path), "tape_digest": self.digest})
        self.assertFalse(summary["ok"])
        self.assertTrue(summary["tape_missing"])

    def test_the_lab_box_resends_a_tape_its_disk_corrupted(self):
        sail = BatchSail(self.root / "boxes")
        sail.boxes["sb_lab"] = {"status": "running", "egress": None, "files": {}, "name": "ltcm-lab"}
        sandbox = SailSandbox(sail, self.root / "state" / "sandbox.json", image_checkpoint="cp_clean_image")
        box = LabBox.from_config(sandbox, {"lab": {"box_id": "sb_lab"}})
        box.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        where = f"{TAPE_DIR}/{self.digest}.json.gz"
        sail.boxes["sb_lab"]["files"][where] = corrupt(sail.boxes["sb_lab"]["files"][where])
        out = box.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual(out, [single(c, self.tape) for c in self.candidates])
        self.assertEqual(box.stats["uploads"], 2)  # sent again, not failed for ever
        self.assertEqual(gzip.decompress(sail.boxes["sb_lab"]["files"][where]), tape_bytes(self.tape))

    def test_a_local_lab_box_resends_a_corrupt_tape_too(self):
        sandbox = LocalSandbox(self.root / "boxes")
        box = LabBox(sandbox)
        box.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        path = self.root / "boxes" / "lab" / "tapes" / f"{self.digest}.json.gz"
        path.write_bytes(corrupt(path.read_bytes()))
        out = box.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
        self.assertEqual(out, [single(c, self.tape) for c in self.candidates])
        self.assertEqual(box.stats["uploads"], 2)

    def test_a_candidate_the_box_cannot_start_is_not_answered_as_its_own_result(self):
        with patch("league.replay.os.fork", side_effect=OSError(11, "Resource temporarily unavailable")):
            results = run_batch(self.candidates, self.tape, workers=2)
            summary = _main_batch({"candidates": self.candidates, "tape": self.tape, "workers": 2})
        self.assertEqual([r["id"] for r in results], [c["id"] for c in self.candidates])
        for result in results:
            self.assertTrue(not_evaluated(result), result)
            self.assertTrue(result["infrastructure"])
            self.assertTrue(result["error"].startswith(NOT_STARTED))
            self.assertFalse(result["ok"])
        self.assertEqual(summary["evaluated"], 0)  # the box counts none of them as judged


class BoundBox(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.state = self.root / "state" / "sandbox.json"
        self.sail = TimedBatchSail(self.root / "boxes")
        self.tape = small("alpaca")
        self.candidates = seed_candidates("alpaca")[:2]

    def tearDown(self):
        self.dir.cleanup()

    def test_a_terminated_lab_box_is_never_replaced_from_the_agents_image(self):
        self.sail.boxes["sb_lab"] = {"status": "terminated", "egress": SEALED, "files": {}, "name": "ltcm-lab"}
        for _ in range(2):  # the House, then the House after a restart that binds it again
            sandbox = SailSandbox(self.sail, self.state, image_checkpoint="cp_clean_image")
            box = LabBox.from_config(sandbox, {"lab": {"box_id": "sb_lab"}})
            with self.assertRaises(BoundBoxGone):
                box.evaluate(self.candidates, "reg:alpaca", self.tape, stake=200.0, limits=LIMITS)
            self.assertEqual(sandbox.bound("lab"), "sb_lab")
        self.assertNotIn("from_checkpoint", self.sail.names())
        # An agent's terminated box is still replaced, as before.
        self.sail.boxes["sb_agent"] = {"status": "terminated", "egress": SEALED, "files": {}, "name": "league-a"}
        sandbox._state["boxes"]["a"] = "sb_agent"
        sandbox._ensure("a")
        self.assertIn("from_checkpoint", self.sail.names())

    def test_a_busy_lab_box_refuses_within_patience_and_its_sail_calls_are_bounded(self):
        self.sail.boxes["sb_lab"] = {"status": "running", "egress": None, "files": {}, "name": "ltcm-lab"}
        sandbox = SailSandbox(self.sail, self.state, image_checkpoint="cp_clean_image")
        sandbox.bind("lab", "sb_lab")
        digest = tape_digest(self.tape)
        held, done = threading.Event(), threading.Event()

        def hold():
            with sandbox.claim("lab") as ok:
                self.assertTrue(ok)
                held.set()
                done.wait(10)

        holder = threading.Thread(target=hold)
        holder.start()
        self.addCleanup(holder.join)
        self.addCleanup(done.set)
        self.assertTrue(held.wait(5))
        started = time.monotonic()
        with sandbox.patience(0.1), self.assertRaises(SandboxBusy):
            sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=digest, stake=200.0, limits=LIMITS)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(self.sail.calls, [])  # nothing ran, nothing was sent
        done.set()
        holder.join(5)
        run = sandbox.replay_batch("lab", self.candidates, self.tape, tape_digest=digest, stake=200.0, limits=LIMITS)
        self.assertEqual(run.result["results"], [single(c, self.tape) for c in self.candidates])
        timeouts = {call: timeout for call, _, timeout in self.sail.timeouts}
        self.assertEqual(set(timeouts), {"upload", "download"})
        self.assertTrue(all(t is not None and t <= SailSandbox.UPLOAD_TIMEOUT + 60 for c, _, t in self.sail.timeouts if c == "upload"))
        self.assertEqual(timeouts["download"], SailSandbox.DOWNLOAD_TIMEOUT)


class ServicePath(unittest.TestCase):
    """`service.build`, the floor's own path, over a fake Sail client: the lab box config.json names
    is bound into the House's sandbox, and the lab evaluates on that very box."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)  # registered first, so it runs after every House is closed
        self.root = Path(self.dir.name)
        self.sail = BatchSail(self.root / "sail")
        # As scripts/lab_box.py leaves it: asleep, its build-time egress still on the record.
        self.sail.boxes[CONFIG_BOX] = {"status": "sleeping", "egress": ["deb.debian.org"], "files": {}, "name": "ltcm-lab"}
        base = service.load_config()
        self.config = {**base, "feeds": False, "options_history": False, "jev": {"enabled": False}, "real_money": False}

    def build(self, **kw):
        def no_network(*args, **kwargs):
            raise OSError("no network in tests")

        with patch("ltcm.sailbox.SailboxClient", return_value=self.sail), patch.object(service, "load_env"), \
                patch.object(service, "secret", return_value="t" * 40), \
                patch("league.venues.gateway_broker", side_effect=lambda venue, **_: FakeBroker(venue)), \
                patch("urllib.request.urlopen", side_effect=no_network):
            house = service.build(self.root / "house", config=kw.pop("config", self.config), research=False, publish=False,
                                  merton=False, **kw)
        self.addCleanup(house.close, wait=None)
        if house.lab is not None:
            self.addCleanup(house.lab.close)
        return house

    def test_the_service_binds_the_configured_lab_box_and_the_lab_evaluates_on_it(self):
        house = self.build()
        self.assertIsInstance(house.lab, Lab)
        box = house.lab.box
        self.assertIsInstance(box, LabBox)
        self.assertEqual(house.settings.lab_box, "lab")
        self.assertEqual((box.box_key, house.lab.box_key), ("lab", "lab"))
        self.assertIs(box.sandbox, house.sandbox)
        self.assertEqual(house.sandbox.bound("lab"), CONFIG_BOX)  # config["lab"]["box_id"], bound
        self.assertEqual(box.holdout, house.holdout_window)
        self.assertEqual(self.sail.calls, [])  # binding is a record, not a Sail call
        tape, candidates = small("alpaca"), seed_candidates("alpaca")[:2]
        out = box.evaluate(candidates, "reg:alpaca", tape, stake=200.0, limits=LIMITS)
        self.assertEqual(out, [single(c, tape) for c in candidates])
        names = self.sail.names()
        self.assertNotIn("from_checkpoint", names)  # the lab box, never an agent-sized one
        self.assertLess(self.sail.calls.index(("set_egress", CONFIG_BOX, SEALED)), names.index("upload"))
        self.assertTrue(all(e["box"] == CONFIG_BOX and e["egress"] == SEALED for e in self.sail.execs))
        # A restart binds the same box again, and makes none.
        again = self.build()
        self.assertEqual(again.sandbox.bound("lab"), CONFIG_BOX)
        self.assertNotIn("from_checkpoint", self.sail.names())

    def test_no_lab_on_a_canary_or_without_a_box_id(self):
        self.assertEqual(service.lab_box_key({"lab": {"box": "ltcm-lab"}}), "")  # a name binds nothing
        self.assertEqual(service.lab_box_key(self.config), "lab")
        no_id = {**self.config, "lab": {k: v for k, v in self.config["lab"].items() if k != "box_id"}}
        self.assertIsNone(self.build(config=no_id).lab)
        self.assertIsNone(self.build(canary=True).lab)
        self.assertEqual(self.sail.calls, [])


class LabOnItsBox(LabCase):
    def failing_box(self, exc):
        class Failing(FakeBox):
            def evaluate(self, candidates, tape_id, tape, **kw):
                raise exc

        return Failing()

    def alerts(self, level=None):
        return [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if level is None or e.payload["level"] == level]

    def test_a_gone_lab_box_stops_the_lab_loudly_and_for_an_hour(self):
        ident = self.queue(KNOB)
        self.lab.use_box(self.failing_box(BoundBoxGone("lab: its bound box sb_lab is terminated")))
        self.assertIsNone(self.lab.evaluate_batch())
        self.assertEqual(self.candidate(ident)["status"], "queued")
        self.assertTrue(any("the Alpha Lab is stopped: its box is gone" in t for t in self.alerts("error")), self.alerts())
        self.clock.advance(1800)
        self.assertTrue(self.lab.box_down())
        self.assertIn("lab box", self.lab.open())
        self.clock.advance(1801)
        self.assertFalse(self.lab.box_down())

    def test_candidates_the_box_could_not_start_stay_queued_and_the_box_rests(self):
        ident = self.queue(KNOB)

        class NoProcesses(FakeBox):
            def evaluate(self, candidates, tape_id, tape, **kw):
                return [{"ok": False, "error": f"{NOT_STARTED} (BlockingIOError: out of processes)", "infrastructure": True,
                         "id": c["id"]} for c in candidates]

        self.lab.use_box(NoProcesses())
        self.assertIsNone(self.lab.evaluate_batch())
        self.assertEqual(self.candidate(ident)["status"], "queued")  # not failed: not its result
        self.assertTrue(self.lab.box_down())
        self.assertTrue(any("could not start 1 of 1" in t for t in self.alerts("warning")), self.alerts())

    def test_the_lab_never_has_a_real_sandbox_make_it_a_box(self):
        sail = BatchSail(Path(self.dir.name) / "sail")
        sandbox = SailSandbox(sail, Path(self.dir.name) / "sandbox.json", image_checkpoint="cp_clean_image")
        lab = Lab(self.house, mutator=self.luna, leaper=self.sol, path=Path(self.dir.name) / "lab-unbound.sqlite")
        self.addCleanup(lab.close)
        lab.admit(KNOB, niche=self.niche, origin="seed", author="house", lineage="founder:test")
        with patch.object(self.house, "sandbox", sandbox):
            self.assertIsNone(lab.evaluate_batch())
        self.assertEqual(sail.calls, [])  # no box made from the agents' image
        self.assertTrue(lab.box_down())
        self.assertTrue(any("no lab box is bound" in t for t in self.alerts("warning")), self.alerts())

    def test_the_use_box_key_is_the_labs(self):
        box = LabBox(self.house.sandbox, box_key="ltcm-lab")
        self.lab.use_box(box)
        self.assertEqual(self.lab.box_key, "ltcm-lab")

    def test_the_lab_does_not_run_while_stopped_deploying_or_below_the_all_tier(self):
        cases = ((patch.object(self.house, "stopped", return_value=True), "stopped"),
                 (patch.object(self.house, "deploying", return_value=True), "release"),
                 (patch.object(self.house, "paused", return_value={"reason": "test"}), "pause"),
                 (patch.object(self.house, "frontier_tier", return_value="code"), "tier"))
        for patcher, words in cases:
            with patcher, patch.object(self.lab, "step") as step:
                self.assertFalse(self.lab.tick(open_for_business=True))
                self.house.wait()
                step.assert_not_called()
                self.assertIn(words, self.lab.refusal)
        # A step that finds the House paused from its start evaluates, breeds and graduates nothing.
        self.queue(KNOB)
        with patch.object(self.house, "paused", return_value={"reason": "test"}):
            out = self.lab.step()
        self.assertEqual((out["batches"], out["evaluated"], out["calls"], out["graduations"]), (0, 0, 0, []))
        self.assertEqual(self.box.calls, [])
        self.assertEqual(self.luna.asked, [])

    def test_the_lab_opens_the_sealed_holdout_only_through_the_house(self):
        tree = ast.parse(Path(lab_module.__file__).read_text(encoding="utf-8"))
        called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        doors = {name for name in called if "holdout" in name.lower() or "seal" in name.lower() or "history" in name.lower()}
        # Its own ledger counts (`seal.used`, `_holdouts_used`, `_lineage_holdouts`, `_holdout_refusal`
        # with the House's `_seal_applies`, a predicate on an agent's NEEDS), its tape check, and the
        # House's one door. Nothing reads the history store or evaluates a seal itself.
        self.assertEqual(doors, {"house._holdout", "HoldoutSeal", "seal.used", "self._holdouts_used", "self._lineage_holdouts",
                                 "self._holdout_refusal", "house._seal_applies", "holdout.get", "SealedTape"})
        self.assertNotIn(".evaluate(", "".join(n for n in called if "seal" in n.lower()))


class LabBirthsOnSail(StalledSailCase):
    """The review of PR 160: `Lab._birth` held the House's lifecycle lock -- which every wake of the
    tick takes -- through the child's NEEDS probe in the probe box and the displaced agent's
    `retire`. Here the House runs on the real `SailSandbox` over the stalling fake client."""

    def setUp(self):
        super().setUp()
        self.house.pacer.may_spend = lambda kind: True
        self.house.game["lab"] = {**(self.house.game.get("lab") or {}), "enabled": True, "stats_every_minutes": 0}
        self.lab = Lab(self.house, box=FakeBox(), mutator=FakeModel("gpt-6-luna", []), leaper=FakeModel("gpt-6-sol", []))
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        self.niche = self.house.niches[DESK]
        self.under_lock: list[str] = []
        lock = self.house._lifecycle_lock
        self.sail.observer = lambda name: self.under_lock.append(name) if lock._is_owned() else None

    def seated(self, name, code):
        agent = self.house.spawn(name, "test-family", code, reason="a test agent")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def graduates(self):
        return [a for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")]

    def evolve(self):
        self.lab.admit(KNOB, niche=self.niche, origin="luna", author="luna", lineage="founder:test")
        self.lab.evaluate_batch()

    def test_a_birth_that_displaces_makes_no_sail_call_under_the_lifecycle_lock(self):
        self.evolve()
        self.niche.max_members = 1
        resident = self.seated("resident", IDLE)
        self.house.sandbox.needs(resident.id, IDLE)  # the resident has a box of its own to retire
        box = self.house.sandbox.box_of(resident.id)
        self.under_lock.clear()
        with patch.object(self.house, "_weakest", return_value=resident):
            out = self.lab.graduate()
        self.assertEqual([o["state"] for o in out], ["born"])
        self.assertEqual(len(self.graduates()), 1)
        self.assertFalse(self.house.registry.get(resident.id).alive)
        self.assertEqual(self.sail.boxes[box]["status"], "terminated")  # retired, outside the lock
        self.assertEqual(self.under_lock, [], "a Sail call was made under the lifecycle lock by the lab's birth")

    def test_a_busy_probe_box_makes_the_birth_wait_and_never_the_tick(self):
        self.evolve()
        passed = {"counted_as_trial": True, "passed": True, "numbers": {}, "needs": static_literal(KNOB, "NEEDS"),
                  "params": {"notional": 50.0}}
        self.house.settings.probe_wait_seconds = 3.0
        held, free = threading.Event(), threading.Event()

        def background():  # other work in the probe box, as a hypothesis replay holds it
            with self.house.sandbox.claim(PROBE_BOX) as ok:
                self.assertTrue(ok)
                held.set()
                free.wait(20)

        holder = threading.Thread(target=background)
        holder.start()
        self.addCleanup(holder.join, 20)
        self.addCleanup(free.set)
        self.assertTrue(held.wait(5))
        real_claim = self.house.sandbox.claim
        asking = threading.Event()

        def claim(agent, *, wait=0.0):
            if agent == PROBE_BOX and threading.current_thread() is lab_thread:
                asking.set()
            return real_claim(agent, wait=wait)

        outcome: list = []
        lab_thread = threading.Thread(target=lambda: outcome.append(self.lab.graduate()))
        with patch.object(self.house, "_candidate_replay", return_value=passed), patch.object(self.house.sandbox, "claim", new=claim):
            lab_thread.start()
            self.assertTrue(asking.wait(5), "the birth never asked for the probe box")
            # While the lab waits for the probe box it holds no lifecycle lock: a tick runs through.
            lock = self.house._lifecycle_lock
            self.assertTrue(lock.acquire(timeout=1.0), "the lab held the lifecycle lock while it waited for the probe box")
            lock.release()
            with patch.object(self.lab, "tick", return_value=False):  # this tick schedules no lab step of its own
                summary, seconds = self.timed_tick()
            self.assertLess(seconds, BOUNDED)
            lab_thread.join(10)
        self.assertFalse(lab_thread.is_alive())
        self.assertEqual([o["state"] for o in outcome[0]], ["waiting_probe"])
        self.assertEqual(self.lab._q("SELECT state FROM graduations")[0]["state"], "passed")  # tried again next step
        self.assertEqual(self.graduates(), [])
        free.set()
        holder.join(5)
        out = self.lab.graduate()
        self.assertEqual([o["state"] for o in out], ["born"])
        self.assertEqual(len(self.graduates()), 1)
        self.assertEqual(self.under_lock, [])


if __name__ == "__main__":
    unittest.main()

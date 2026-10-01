"""The gate's data, Oct 1, 2026 (league/swarm/settings.py `ready_refusal`, pool.py's holdout coverage, gate.py's owed look).

Sept 29-30: the nightly forward chain extended the five-root gate image while `swarm.json` named the 25-root one, and its
ready file replaced the 25-root gate without a check; every gate box advertised every root without looking; three looks of
a GOOGL/MSFT program failed with "no holdout days for GOOGL, MSFT", each counted as a try, and the third barred the
program from the incubator although no verdict was made. These tests fail on the code before that fix."""

from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.gate import Gate, run_sha
from league.swarm.pool import HOLDOUT_FIRST, HOLDOUT_LAST, PoolError
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.test_swarm_pool import PoolCase, job
from league.tests.test_swarm_rounds import FakeGymPool, RoundCase
from league.tests.swarm_fakes import FakeSail

NAMED = "sbcp_gate25"
ROOTS = ["SPY", "QQQ", "GOOGL", "MSFT"]
READY = {"schema": 1, "day": "2026-09-29", "ready_at": "2026-09-30T06:12:32+00:00", "gate_checkpoint": "sbcp_chain29",
         "roots": ["GOOGL", "MSFT", "QQQ", "SPY"]}


class ReadyFile(unittest.TestCase):
    """THE CHAIN'S RULE: the nightly's ready file stands in for swarm.json's gate only while it extends that gate."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": NAMED, "roots": ROOTS}}))

    def load(self, ready=None, images=None):
        if ready is not None:
            (self.root / "gym-forward.json").write_text(ready if isinstance(ready, str) else json.dumps(ready))
        if images is not None:
            (self.root / "data").mkdir(exist_ok=True)
            (self.root / "data" / "images.json").write_text(json.dumps(images))
        return S.load(self.root, config={})

    def test_a_chain_that_extends_the_named_gate_and_holds_every_root_stands_in_for_it(self):
        loaded = self.load({**READY, "base_checkpoint": NAMED, "holdout_roots": ROOTS + ["TSLA"]})
        self.assertEqual(loaded["gym"]["gate_checkpoint"], "sbcp_chain29")
        self.assertEqual(loaded["forward"]["ready"]["day"], "2026-09-29")
        self.assertNotIn("ready_ignored", loaded["forward"])

    def test_a_chain_on_another_gate_image_is_ignored_and_says_why(self):
        loaded = self.load({**READY, "base_checkpoint": "sbcp_core5", "holdout_roots": ROOTS})
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED, "swarm.json's gate, not the five-root chain")
        self.assertNotIn("ready", loaded["forward"])
        self.assertIn("extends sbcp_core5", loaded["forward"]["ready_ignored"]["why"])

    def test_a_chain_whose_gate_lacks_a_root_of_the_swarm_is_ignored(self):
        loaded = self.load({**READY, "base_checkpoint": NAMED, "holdout_roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"]})
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertIn("no holdout for GOOGL, MSFT", loaded["forward"]["ready_ignored"]["why"])
        loaded = self.load({**READY, "base_checkpoint": NAMED})  # no list of its roots at all
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)

    def test_a_legacy_file_stands_only_when_images_json_proves_its_chain(self):
        legacy = dict(READY)  # what the nightly wrote before it named its base (production's file at the switch)
        self.assertEqual(self.load(legacy)["gym"]["gate_checkpoint"], NAMED, "no images.json: nothing proves the chain")
        core = {"gate": {"current": {"checkpoints": ["sbcp_core5"], "roots": None}, "current_checkpoint": "sbcp_chain29",
                         "forward_days": {"2026-09-29": {"checkpoint": "sbcp_chain29"}}}}
        loaded = self.load(legacy, core)  # Sept 30: images.json's gate was the core-five image
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertIn("not the gate swarm.json names", loaded["forward"]["ready_ignored"]["why"])
        rebased = {"gate": {"current": {"checkpoints": [NAMED, "sbcp_gate25b"], "roots": ROOTS + ["TSLA"]},
                            "current_checkpoint": "sbcp_chain29", "forward_days": {"2026-09-29": {"checkpoint": "sbcp_chain29"}}}}
        loaded = self.load(legacy, rebased)  # Oct 1, after the operator's re-base: production keeps its chain
        self.assertEqual(loaded["gym"]["gate_checkpoint"], "sbcp_chain29")
        self.assertNotIn("ready_ignored", loaded["forward"])
        off_tip = json.loads(json.dumps(rebased))
        off_tip["gate"]["current_checkpoint"] = "sbcp_chain30"
        self.assertEqual(self.load(legacy, off_tip)["gym"]["gate_checkpoint"], NAMED, "not the chain's tip: not proven")
        short = json.loads(json.dumps(rebased))
        short["gate"]["current"]["roots"] = ["SPY", "QQQ"]
        self.assertEqual(self.load(legacy, short)["gym"]["gate_checkpoint"], NAMED)

    def test_an_unreadable_ready_file_never_moves_the_gate_and_a_missing_one_is_no_news(self):
        loaded = self.load("{not json")
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertIn("cannot be read", loaded["forward"]["ready_ignored"]["why"])
        (self.root / "gym-forward.json").unlink()
        loaded = self.load()
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertNotIn("ready_ignored", loaded["forward"])

    def test_the_loop_raises_one_alert_for_each_ignored_ready_file(self):
        from league.swarm.loop import Swarm

        store = SwarmStore(self.root)
        self.addCleanup(store.close)
        stub = types.SimpleNamespace(settings=self.load({**READY, "base_checkpoint": "sbcp_core5", "holdout_roots": ROOTS}),
                                     store=store)
        first = Swarm.gate_chain_notice(stub)
        self.assertEqual((first["action"], first["alert"]), ("gate_chain_ignored", True))
        self.assertIsNone(Swarm.gate_chain_notice(stub), "once, not every loop")
        stub.settings = self.load({**READY, "day": "2026-09-30", "ready_at": "2026-10-01T06:10:00+00:00",
                                   "base_checkpoint": "sbcp_core5", "holdout_roots": ROOTS})
        self.assertIsNotNone(Swarm.gate_chain_notice(stub), "a new ready file ignored is news again")
        alerts = [e for e in store.events_after(0) if e["payload"].get("action") == "gate_chain_ignored"]
        self.assertEqual(len(alerts), 2)


class ListingSail(FakeSail):
    """Sail with a command runner: a gate box's holdout listing answers `listing`."""

    def __init__(self, listing, code=0):
        super().__init__()
        self.listing, self.code, self.commands = listing, code, []

    def exec(self, box, command, *, timeout=600, **kw):
        self.commands.append(command)
        return types.SimpleNamespace(return_code=self.code, stdout=json.dumps(self.listing) + "\n", stderr="")


class GateBoxCoverage(PoolCase):
    """THE GATE'S HOLDOUT COVERAGE: a gate box lists its holdout by file name at start; a look it cannot make fails at once
    as missing data, and the gate image's coverage is kept for the gate to read before a look."""

    FULL = {"nbbo": 184, "underlying": 184}

    def gate_box(self, listing):
        self.sail = ListingSail(listing)
        pool = self.pool(roots=ROOTS)
        pool.submit(job("g", window="holdout", roots=("GOOGL",), gate="holdout look g v1"))
        pool.manage()
        return pool, [b for b in pool.boxes.values() if b.kind == "gate"]

    def test_a_gate_box_that_lacks_a_root_fails_that_look_at_once_as_missing_data(self):
        pool, [box] = self.gate_box({"SPY": self.FULL, "QQQ": self.FULL, "GOOGL": {"nbbo": 0, "underlying": 0},
                                     "MSFT": {"nbbo": 184, "underlying": 0}})
        self.assertEqual(box.holdout, ("QQQ", "SPY"))
        [command] = self.sail.commands
        self.assertIn(HOLDOUT_FIRST, command)
        self.assertNotIn("--gate", command, "file names only: the gate's capability is never minted")
        [look] = list(pool.queue)
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError):
            pool.wait(look, 0)
        self.assertEqual(look.missing, ("GOOGL",))
        self.assertEqual([c for c in self.calls if c["window"] == "holdout"], [], "the Gym never ran it")
        coverage = pool.holdout_coverage()
        self.assertEqual((coverage["roots"], coverage["box"]), (["QQQ", "SPY"], box.id))
        alerts = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "gate_coverage"]
        self.assertEqual([a["missing"] for a in alerts], [["GOOGL", "MSFT"]])
        self.assertEqual(self.store.boxes(kind="gate")[0]["detail"]["holdout_roots"], ["QQQ", "SPY"])

    def test_a_gate_box_whose_store_holds_no_holdout_is_not_used(self):
        pool, boxes = self.gate_box({"SPY": {"nbbo": 0, "underlying": 0}})
        self.assertEqual(boxes, [])
        self.assertEqual(len(self.sail.terminated), 1)

    def test_the_gyms_own_missing_data_answer_is_kept_for_the_gate_image(self):
        class GymDataMissing(Exception):
            pass

        pool = self.pool(roots=ROOTS)
        box = self.ready_box(pool, "gate")
        box.roots = tuple(ROOTS)  # advertised, as every gate box did before Oct 1
        self.failure = GymDataMissing("the box is missing data: no holdout days for GOOGL in /data/store")
        look = pool.submit(job("g", window="holdout", roots=("GOOGL", "SPY"), gate="holdout look g v1"))
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError):
            pool.wait(look, 0)
        self.assertEqual(look.missing, ("GOOGL",))
        self.assertEqual(pool.holdout_coverage()["missing"], ["GOOGL"])

    def test_the_holdout_window_is_the_gyms(self):
        from league.gym.day import WINDOWS

        self.assertEqual((HOLDOUT_FIRST, HOLDOUT_LAST), tuple(d.isoformat() for d in WINDOWS["holdout"]))


class CoveragePool(FakeGymPool):
    """The rounds' fake pool, with what the real pool knows of the gate image and a Gym that lacks a root's holdout."""

    def __init__(self, answer):
        super().__init__(answer)
        self.coverage = None
        self.missing: tuple[str, ...] | None = None

    def holdout_coverage(self, image=None):
        return self.coverage

    def wait(self, job, timeout=None, late=None, late_fail=None):
        if self.missing and job.window == "holdout":
            job.missing = self.missing
            raise PoolError(f"the Gym is missing data: the box is missing data: no holdout days for "
                            f"{', '.join(self.missing)} in /data/store")
        return super().wait(job, timeout, late, late_fail)


class GateMissingData(RoundCase):
    """MISSING DATA IS THE GATE IMAGE'S, NOT THE PROGRAM'S."""

    def setUp(self):
        super().setUp()
        self.pool = CoveragePool(lambda job: self.answer(job))
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2  # the review and the audit, once
        self.sha = run_sha(self.store.version("a", 1))

    def holdout_jobs(self):
        return [j for j in self.pool.jobs if j.window == "holdout"]

    def alerts(self, action):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status" and e["payload"].get("alert")
                and e["payload"].get("action") == action]

    def rounds(self, n):
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        for _ in range(n):
            out = gate.run()
            self.clock.advance(300)
        return out

    def assert_owed_untouched(self):
        state = self.store.family("a")["state"]
        self.assertEqual((state.get("gate_ready"), state.get("look_inflight"), state.get("gated_sha")), (True, None, None))
        self.assertEqual(self.store.get("look_tries:" + self.sha, 0), 0, "no try counted")
        self.assertEqual((self.store.refusals("a"), self.store.looks()), ([], []))
        self.assertFalse(state.get("incubator_barred"), "no verdict, no incubator bar")
        self.assertEqual(self.alerts("look_failed_three_times"), [])

    def test_a_look_whose_roots_the_gate_image_lacks_is_refused_up_front_with_one_alert(self):
        self.pool.coverage = {"roots": ["QQQ"], "missing": []}
        out = self.rounds(3)
        self.assertEqual(self.holdout_jobs(), [], "no look is started")
        self.assertIn("a", out["waiting"])
        self.assert_owed_untouched()
        [alert] = self.alerts("gate_missing_data")
        self.assertEqual(alert["missing"], ["SPY"])
        self.pool.coverage = {"roots": ["QQQ", "SPY"], "missing": []}  # the gate image is fixed: the look runs
        self.rounds(1)
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_root_the_gym_said_was_missing_is_refused_up_front_too(self):
        self.pool.coverage = {"roots": None, "missing": ["SPY"]}
        self.rounds(2)
        self.assertEqual(self.holdout_jobs(), [])
        self.assert_owed_untouched()

    def test_the_ready_files_holdout_roots_refuse_a_look_while_its_chain_is_the_gate(self):
        self.settings["forward"]["ready"] = {**READY, "gate_checkpoint": "sbcp_gate", "holdout_roots": ["QQQ"]}
        self.rounds(2)
        self.assertEqual(self.holdout_jobs(), [])
        self.assert_owed_untouched()

    def test_a_look_that_fails_for_missing_data_counts_no_try_and_is_never_refused(self):
        self.pool.missing = ("SPY",)  # what the pool knows says nothing: the look runs and the Gym lacks the root
        self.rounds(4)
        self.assertEqual(len(self.holdout_jobs()), 4)
        self.assert_owed_untouched()
        self.assertEqual(len(self.alerts("gate_missing_data")), 1)
        failed = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "look_failed"]
        self.assertEqual(failed[0]["missing_data"], ["SPY"])

    def test_a_missing_data_failure_after_its_waiter_gave_up_counts_no_try(self):
        self.pool.slow.add("a")
        self.rounds(1)
        job, _ = self.pool.landing[0]
        job.missing = ("SPY",)
        job.late_fail("the Gym is missing data: no holdout days for SPY in /data/store")
        self.assert_owed_untouched()

    def test_from_the_third_try_on_every_failure_is_an_alert(self):
        self.store.put("look_tries:" + self.sha, 3)  # the same program failed three times in a family since retired
        self.pool.fail.add("a")
        self.rounds(1)
        state = self.store.family("a")["state"]
        self.assertEqual((state.get("gated_sha"), state.get("gate_ready")), (self.sha, False), "parked")
        [alert] = self.alerts("look_failed_three_times")
        self.assertEqual(alert["tries"], 4, "a fourth failure is never silent")
        self.assertEqual(self.store.refusals("a"), [], "its program was refused at the third try, not again")


if __name__ == "__main__":
    unittest.main()

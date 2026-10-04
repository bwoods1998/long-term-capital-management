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

from league.swarm import bands
from league.swarm import settings as S
from league.swarm.gate import Gate, run_sha
from league.swarm.pool import HOLDOUT_FIRST, HOLDOUT_LAST, PoolError
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.test_swarm_pool import PoolCase, job
from league.tests.test_swarm_rounds import FakeGymPool, RoundCase, strong
from league.tests.swarm_fakes import FakeSail

NAMED = "sbcp_gate25"
ROOTS = ["SPY", "QQQ", "GOOGL", "MSFT"]
READY = {"schema": 1, "day": "2026-09-29", "ready_at": "2026-09-30T06:12:32+00:00", "gate_checkpoint": "sbcp_chain29",
         "roots": ["GOOGL", "MSFT", "QQQ", "SPY"]}
BUILT = "2026-09-27T12:04:44Z"  # when the named image was built (a staging build, adopted on Oct 1)


def rebased():
    """images.json after the operator's Oct 1 re-base: the named image is current, its chain reset, and the nightly (the
    release before this one) re-copied 09-28 and 09-29 onto it with no `base` on their records."""
    return {"gate": {"current": {"checkpoints": [NAMED, "sbcp_gate25b"], "roots": ROOTS + ["TSLA"], "built_at": BUILT},
                     "current_checkpoint": "sbcp_chain29",
                     "checkpoints": [{"id": "sbcp_chain28", "day": "2026-09-28", "at": "2026-10-01T06:20:00+00:00"},
                                     {"id": "sbcp_chain29", "day": "2026-09-29", "at": "2026-10-01T06:31:00+00:00"}],
                     "forward_days": {"2026-09-28": {"checkpoint": "sbcp_chain28", "adopted": "2026-10-01T06:19:00+00:00"},
                                      "2026-09-29": {"checkpoint": "sbcp_chain29", "adopted": "2026-10-01T06:30:00+00:00"}}}}


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
        loaded = self.load(legacy, rebased())  # Oct 1, after the operator's re-base: production keeps its chain
        self.assertEqual(loaded["gym"]["gate_checkpoint"], "sbcp_chain29")
        self.assertNotIn("ready_ignored", loaded["forward"])
        short = rebased()
        short["gate"]["current"]["roots"] = ["SPY", "QQQ"]
        self.assertEqual(self.load(legacy, short)["gym"]["gate_checkpoint"], NAMED)
        other_day = rebased()
        other_day["gate"]["forward_days"]["2026-09-29"]["checkpoint"] = "sbcp_chain28"
        self.assertEqual(self.load(legacy, other_day)["gym"]["gate_checkpoint"], NAMED, "not its day's checkpoint")
        unlisted = rebased()
        unlisted["gate"]["checkpoints"] = unlisted["gate"]["checkpoints"][:1]
        self.assertEqual(self.load(legacy, unlisted)["gym"]["gate_checkpoint"], NAMED, "not on the chain's records")

    def test_a_legacy_file_stands_while_the_nightly_records_the_next_day_before_publishing_it(self):
        # The first night of this release: the nightly records 09-30's checkpoint (named on its base) and makes it the
        # chain's tip a minute before it publishes 09-30. The legacy 09-29 file is no longer the tip, and still the gate.
        night = rebased()
        night["gate"]["checkpoints"].append({"id": "sbcp_chain30", "day": "2026-09-30", "at": "2026-10-01T07:02:00+00:00",
                                             "base": NAMED})
        night["gate"]["current_checkpoint"] = "sbcp_chain30"
        loaded = self.load(dict(READY), night)
        self.assertEqual(loaded["gym"]["gate_checkpoint"], "sbcp_chain29", "no switch to the bare gate and back")
        self.assertNotIn("ready_ignored", loaded["forward"])
        night["gate"]["checkpoints"][-1]["base"] = "sbcp_core5"  # the chain moved to another image after 09-29
        loaded = self.load(dict(READY), night)
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertIn("extends sbcp_core5", loaded["forward"]["ready_ignored"]["why"])

    def test_a_stale_chain_never_passes_for_a_gate_adopted_without_its_reset(self):
        # `images.py build gate` (or `finish`) records the named image as current, built now, and leaves the chain
        # records of the image before it: a legacy file on that chain is another image's, however its tip looks.
        stale = rebased()
        stale["gate"]["current"]["built_at"] = "2026-10-02T09:00:00Z"
        loaded = self.load(dict(READY), stale)
        self.assertEqual(loaded["gym"]["gate_checkpoint"], NAMED)
        self.assertIn("not adopted after", loaded["forward"]["ready_ignored"]["why"])
        self.assertIsNotNone(S.chain_refusal(stale["gate"], "sbcp_chain29"))
        undated = rebased()
        del undated["gate"]["current"]["built_at"]
        self.assertEqual(self.load(dict(READY), undated)["gym"]["gate_checkpoint"], NAMED, "nothing dates the image")
        # The lineage itself: the image's own checkpoints, entries named on it, and entries taken after it was recorded.
        gate = rebased()["gate"]
        self.assertIsNone(S.chain_refusal(gate, NAMED))
        self.assertIsNone(S.chain_refusal(gate, "sbcp_chain28"))
        gate["checkpoints"][1]["at"] = "2026-09-26T06:00:00+00:00"  # a later entry from before the image
        self.assertIsNotNone(S.chain_refusal(gate, "sbcp_chain28"))
        self.assertIsNotNone(S.chain_refusal(gate, "sbcp_elsewhere"))

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
        self.look = pool.submit(job("g", window="holdout", roots=("GOOGL",), gate="holdout look g v1"))
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

    def test_a_gate_box_whose_store_holds_no_holdout_is_not_used_and_the_look_waiting_fails_as_missing_data(self):
        pool, boxes = self.gate_box({"SPY": {"nbbo": 0, "underlying": 0}})
        self.assertEqual(boxes, [])
        self.assertEqual(len(self.sail.terminated), 1)
        self.assertEqual(pool.holdout_coverage()["roots"], [], "the image holds none: the gate refuses looks up front")
        self.assertEqual(list(pool.queue), [], "not left to be abandoned (a counted try)")
        look = self.look
        self.assertEqual(look.missing, ("GOOGL",))
        with self.assertRaises(PoolError):
            pool.wait(look, 0)

    def test_a_root_copied_in_part_is_not_taken_for_its_whole_holdout(self):
        pool, [box] = self.gate_box({"SPY": self.FULL, "QQQ": self.FULL, "MSFT": self.FULL,
                                     "GOOGL": {"nbbo": 184, "underlying": 97}})
        self.assertEqual(box.holdout, ("MSFT", "QQQ", "SPY"))
        self.assertEqual(pool.holdout_coverage()["roots"], ["MSFT", "QQQ", "SPY"])

    def test_a_store_fault_that_names_no_root_is_not_missing_data(self):
        class GymDataMissing(Exception):
            pass

        pool = self.pool(roots=ROOTS)
        box = self.ready_box(pool, "gate")
        box.roots = tuple(ROOTS)
        self.failure = GymDataMissing("no store at /data/store (no VERSION file)")
        look = pool.submit(job("g", window="holdout", roots=("GOOGL", "SPY"), gate="holdout look g v1"))
        pool.run_batch(box, pool._take(box))
        with self.assertRaises(PoolError):
            pool.wait(look, 0)
        self.assertIsNone(look.missing, "a fault of the box: its look counts a try, as before")
        self.assertIsNone(pool.holdout_coverage(), "and the image's record is not marked")

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

    def test_an_image_whose_store_holds_no_holdout_refuses_every_look_up_front(self):
        self.pool.coverage = {"roots": [], "missing": []}
        self.rounds(2)
        self.assertEqual(self.holdout_jobs(), [])
        self.assert_owed_untouched()
        [alert] = self.alerts("gate_missing_data")
        self.assertEqual(alert["missing"], ["SPY"], "every root the program needs")

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


class TheProofNamesItsGateBase(RoundCase):
    """L6 (release F1, Oct 3, 2026; `Gate.holdout_base`, `Gate._finish`): the nightly chain moves `gym.gate_checkpoint`
    every night, so the checkpoint a look ran on says nothing of WHICH holdout it read once a night has passed. The
    banded proof of a passed look therefore names the gate image the owner's `swarm.json` names, which the chain
    extends: a later release can prove "the same holdout" by that name. Nothing in this release reads it."""

    def loaded(self, ready=None, images=None, *, named=NAMED):
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"gate_checkpoint": named, "roots": ROOTS}}))
        if ready is not None:
            (self.root / "gym-forward.json").write_text(json.dumps(ready))
        if images is not None:
            (self.root / "data").mkdir(exist_ok=True)
            (self.root / "data" / "images.json").write_text(json.dumps(images))
        return S.load(self.root, config={})

    def base(self, settings):
        return Gate(self.store, self.pool, self.router, settings, clock=self.clock).holdout_base()

    def test_the_base_is_the_named_gate_whichever_checkpoint_of_its_chain_is_in_force(self):
        self.assertEqual(self.base(self.loaded()), NAMED, "no chain: the named gate itself is the gate")
        chain = self.loaded({**READY, "base_checkpoint": NAMED, "holdout_roots": ROOTS})
        self.assertEqual((chain["gym"]["gate_checkpoint"], self.base(chain)), ("sbcp_chain29", NAMED),
                         "the chain's newest checkpoint is the gate, and its base is the named image")
        tonight = self.loaded({**READY, "day": "2026-09-30", "ready_at": "2026-10-01T06:12:32+00:00",
                               "gate_checkpoint": "sbcp_chain30", "base_checkpoint": NAMED, "holdout_roots": ROOTS})
        self.assertEqual((tonight["gym"]["gate_checkpoint"], self.base(tonight)), ("sbcp_chain30", NAMED),
                         "a night later the checkpoint moved and the base did not")
        other = self.loaded({**READY, "base_checkpoint": "sbcp_core5", "holdout_roots": ROOTS})
        self.assertEqual((other["gym"]["gate_checkpoint"], self.base(other)), (NAMED, NAMED),
                         "a chain on another image is ignored: the named gate is the gate")

    def test_a_base_the_settings_cannot_name_is_none(self):
        legacy = self.loaded(dict(READY), rebased())  # a ready file from before the nightly wrote its base, which stands
        self.assertEqual(legacy["gym"]["gate_checkpoint"], "sbcp_chain29")
        self.assertIsNone(self.base(legacy), "its chain is proven by data/images.json, which the settings do not carry")
        self.assertIsNone(self.base({"gym": {"gate_checkpoint": None}, "forward": {}}), "no gate image")
        self.assertIsNone(self.base({}))
        self.assertEqual(self.base({"gym": {"gate_checkpoint": "sbcp_x"}, "forward": {"ready": "not a mapping"}}), "sbcp_x")

    def test_a_passed_looks_proof_names_the_base_beside_the_checkpoint_it_ran_on(self):
        bundle = bands._bundle()
        images = {"gym": "sbcp_gym", "gate": "sbcp_chain29"}
        self.settings["gym"].update(image_checkpoint=images["gym"], gate_checkpoint=images["gate"])
        self.settings["forward"]["ready"] = {**READY, "base_checkpoint": NAMED, "holdout_roots": ROOTS}
        self.pool.image = lambda kind="gym": images["gate" if kind == "gate" else "gym"]
        self.pool.bundle = lambda: bundle
        self.answer = lambda job: {**strong(job), "gym_bundle": bundle,
                                   "gym_image": images["gate" if job.window == "holdout" else "gym"]}
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.assertEqual(gate.run()["looked"], [{"family": "a", "passed": True}])
        fam = self.store.family("a")
        proof = fam["state"]["banded_evaluator"]
        self.assertEqual((fam["band"], proof["holdout_image"], proof["holdout_base"]), ("candidate", "sbcp_chain29", NAMED))
        self.assertTrue(bands.current_banded_evaluator(fam["state"], run_sha(self.store.version("a", 1))),
                        "and the proof is current, as before")
        # The next night: the chain's checkpoint moved. The proof's checkpoint is no longer the gate; its base still is.
        images["gate"] = "sbcp_chain30"
        self.settings["gym"]["gate_checkpoint"] = "sbcp_chain30"
        self.settings["forward"]["ready"] = {**self.settings["forward"]["ready"], "day": "2026-09-30",
                                             "gate_checkpoint": "sbcp_chain30"}
        self.assertNotEqual(proof["holdout_image"], self.settings["gym"]["gate_checkpoint"])
        self.assertEqual(proof["holdout_base"], gate.holdout_base(), "the same holdout, by its named base")


if __name__ == "__main__":
    unittest.main()

"""No paid polling, durable event wakeups, and retirement independent of a refill target."""

from concurrent.futures import ThreadPoolExecutor
import copy
import random
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from league.swarm import evidence, settings
from league.swarm.loop import Scheduler
from league.swarm.seeds import SEEDS, family_spec
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from league.tests.test_swarm_researcher import ResearcherCase


class DurableWaits(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(settings.DEFAULTS)
        self.fid = self.store.add_family(family_spec(SEEDS[0]), origin="seed")["id"]
        self.scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)

    def park(self):
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.store.set_state(self.fid, dormant_cycles=1)
        self.scheduler.release(self.fid, {"hold": True, "dormant_cycles": 1})
        self.assertIsNone(self.scheduler.take(idle_seconds=0))

    def test_elapsed_time_clock_reversal_restart_and_weights_do_not_buy_a_turn(self):
        self.park()
        for elapsed in (300, 1800, 86400, 30 * 86400, -40 * 86400):
            self.clock.advance(elapsed)
            self.assertIsNone(self.scheduler.take(idle_seconds=0))
        self.store.update_family(self.fid, weight=1.0)
        self.store.add_spend("sail_model", 0.01)
        self.scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)
        self.assertIsNone(self.scheduler.take(idle_seconds=0), "a restart preserves the hold")
        self.assertEqual(self.scheduler.waiting(), 1)
        self.assertEqual(self.scheduler.pause(), self.scheduler.MAX_PAUSE)

    def test_each_actionable_event_wakes_a_held_family(self):
        events = [
            lambda: self.store.bump(self.fid, trials=1),
            lambda: self.store.set_state(self.fid, gate_ready=True),
            lambda: self.store.set_state(self.fid, rewrite_ready={"code": "new program"}),
            lambda: self.store.note(self.fid, "The counterfactual test should use the same exposure."),
            lambda: self.store.put("architect_agenda_section", {"text": "Test a different causal mechanism."}),
            lambda: self.settings["gym"].update(image_checkpoint="freshly-verified-data"),
            lambda: self.store.set_state(self.fid, research_wake="operator-evidence-1"),
            lambda: self.store.set_state(self.fid, research_feedback_revision="practice-15"),
        ]
        for event in events:
            self.park()
            event()
            self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
            self.scheduler.release(self.fid, {})
            self.store.set_state(self.fid, rewrite_ready=None)  # the real researcher consumes an offered rewrite

    def test_a_result_landing_during_a_hold_is_not_lost(self):
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.store.bump(self.fid, trials=1)
        self.store.set_state(self.fid, dormant_cycles=1)
        self.scheduler.release(self.fid, {"hold": True, "dormant_cycles": 1})
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)

    def test_material_practice_feedback_wakes_once_per_evidence_block(self):
        row = {"family": self.fid, "program": {"trades": 9, "pnl_usd": 10.0, "returns": [0.1, -0.05, 0.2],
               "daily": [["2026-09-28", 0.1, 1], ["2026-09-29", -0.05, 1], ["2026-09-30", 0.2, 1]]}}
        with patch("league.swarm.practice.summary", return_value={"rows": [row]}):
            self.park()
            row["program"]["trades"] = 10
            self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
            self.scheduler.release(self.fid, {"hold": True})
            row["program"]["trades"] = 11
            self.assertIsNone(self.scheduler.take(idle_seconds=0), "one more trade is not a new paid research turn")
            row["program"]["trades"] = 15
            self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)

    def test_pending_work_remains_runnable_and_a_new_hold_records_its_new_baseline(self):
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.scheduler.release(self.fid, {"hold": True, "pending_run": True})
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.scheduler.release(self.fid, {"hold": True})
        self.assertIsNone(self.scheduler.take(idle_seconds=0))
        self.store.note(self.fid, "A genuinely new diagnostic.")
        self.assertEqual(self.scheduler.take(idle_seconds=0), self.fid)
        self.scheduler.release(self.fid, {"hold": True})
        self.clock.advance(86400)
        self.assertIsNone(self.scheduler.take(idle_seconds=0), "the same note cannot wake it twice")


class PaidPolling(ResearcherCase):
    def test_researcher_hold_is_one_paid_decision_until_new_guidance(self):
        fid = self.fam["id"]
        researcher = self.researcher()
        researcher.cycle(fid)  # existing starter functionality is independent of the model
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Waiting for the missing execution evidence."})]}]
        scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)
        self.assertEqual(scheduler.take(idle_seconds=0), fid)
        out = researcher.cycle(fid)
        self.assertTrue(out["hold"])
        self.assertGreater(out["model_calls"], 0)
        scheduler.release(fid, out)
        calls, cycles, spend = len(self.sail.bodies), self.store.family(fid)["cycles"], self.store.spent()
        for _ in range(48):
            self.clock.advance(3600)
            scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)
            self.assertIsNone(scheduler.take(idle_seconds=0))
        self.assertEqual((len(self.sail.bodies), self.store.family(fid)["cycles"], self.store.spent()), (calls, cycles, spend))
        self.store.note(fid, "The independent execution result has arrived; evaluate the revised hypothesis.")
        self.assertEqual(scheduler.take(idle_seconds=0), fid)


class EvidenceBackedRetirement(ResearcherCase):
    def test_trials_unlock_retirement_before_a_paid_hold_at_start_equal_ceiling(self):
        self.settings["population"].update(start=96, ceiling=96, floor=0)
        fid = self.fam["id"]
        self.store.update_family(fid, trials=10)
        researcher = self.researcher()
        self.assertTrue(researcher.can_retire(self.store.family(fid)))
        self.assertEqual(researcher.retire_floor(self.store.family(fid)), 0)
        out = {}
        result = researcher._execute(self.store.family(fid), "retire", {"reason": "The registered counterfactual refuted the timing mechanism."}, out, author="test")
        self.assertEqual(result["status"], "retired")
        self.assertEqual(self.store.family(fid)["trials"], 10)
        self.assertIn("counterfactual", self.store.graveyard()[0]["lesson"])

    def test_concurrent_retirements_stop_at_floor_and_preserve_all_evidence(self):
        self.settings["population"].update(start=96, ceiling=96, floor=1)
        first = self.fam["id"]
        second = self.store.add_family({**family_spec(SEEDS[0]), "id": "other-tested-family"}, origin="seed")["id"]
        for fid in (first, second):
            self.store.update_family(fid, validations=2, trials=20)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        researchers = [self.researcher(), self.researcher()]
        researchers[1].store = other
        barrier = threading.Barrier(2)

        def retire(researcher, fid):
            fam = researcher.store.family(fid)
            barrier.wait()
            return researcher._execute(fam, "retire", {"reason": "Costs consume the measured effect."}, {}, author="test")["status"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(retire, r, fid) for r, fid in zip(researchers, (first, second))]
            self.assertEqual(sorted(f.result() for f in futures), ["refused", "retired"])
        self.assertEqual(len(self.store.families(alive=True)), 1)
        self.assertEqual(sum(f["trials"] for f in self.store.families()), 40)

    def test_awaited_independent_evidence_cannot_be_retired(self):
        fid = self.fam["id"]
        self.settings["population"]["floor"] = 0
        self.store.update_family(fid, validations=2, trials=100)
        researcher = self.researcher()
        for fields in ({"gate_ready": True}, {"gate_ready": False, "look_inflight": {"sha": "sealed"}},
                       {"look_inflight": None, "gate_hold": "operator", "gate_ready": True},
                       {"gate_hold": None, "gate_ready": False, "validation_version": 1,
                        "extension_hold": {"version": 1, "checks": "6/8"}}):
            self.store.set_state(fid, **fields)
            self.assertFalse(researcher.can_retire(self.store.family(fid)))


class PositiveExploitation(unittest.TestCase):
    def test_negative_validated_families_never_receive_the_reserved_exploit_share(self):
        class MeanDraw(random.Random):
            def gauss(self, mu, sigma):
                return mu

        rows = [{"id": "negative", "validations": 10, "mean": -1.0, "t": -10.0},
                {"id": "new", "validations": 0},
                {"id": "positive", "validations": 2, "mean": 0.1, "t": 2.0}]
        shares = evidence.thompson(rows, rng=MeanDraw())
        self.assertAlmostEqual(shares["positive"], 0.15)
        self.assertAlmostEqual(shares["new"] + shares["negative"], 0.85)
        self.assertGreater(shares["new"], shares["negative"])
        rows[-1]["mean"] = 0.0
        shares = evidence.thompson(rows, rng=MeanDraw())
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertLess(shares["negative"], shares["new"])


class ExperimentAdmission(ResearcherCase):
    CODE = '''NEEDS = {"roots": ["SPY"], "dte": [0, 5]}
PARAMS = {"signal_on": 1, "unused": 1}
def decide(ctx):
    if not PARAMS["signal_on"]:
        return []
    return []
'''

    def test_unread_changed_override_creates_no_run_version_or_trial(self):
        fid = self.fam["id"]
        out = {}
        before = (self.store.versions(fid), self.store.family(fid)["trials"])
        result = self.researcher()._gym_run(self.fam, {"code": self.CODE, "params": {"unused": 2}}, out, author="test")
        self.assertEqual(result["status"], "refused")
        self.assertIn("never read", result["reason"])
        self.assertEqual((self.store.versions(fid), self.store.family(fid)["trials"]), before)
        self.assertEqual(self.pool.jobs, [])

    def test_one_invalid_sweep_variant_refuses_the_whole_sweep_before_spending(self):
        fid = self.fam["id"]
        result = self.researcher()._gym_sweep(self.fam, {"code": self.CODE,
                                            "variants": [{"signal_on": 0}, {"unused": 2}]}, {}, author="test")
        self.assertEqual(result["status"], "refused")
        self.assertIn("never read", result["reason"])
        self.assertEqual((self.store.versions(fid), self.store.family(fid)["trials"], self.pool.jobs), ([], 0, []))

    def test_a_valid_no_trade_baseline_can_still_be_replayed(self):
        result = self.researcher()._gym_run(self.fam, {"code": self.CODE, "params": {"signal_on": 0}}, {}, author="test")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(self.pool.jobs)

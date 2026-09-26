"""The Monday cleanup only owns a durably observed Completion process, never a replacement."""
import copy
import threading
from unittest import mock

from scripts.data import nightly  # makes the tools' local imports available, as their actual CLI does
from scripts.data import burst_cutoff as bc
from league.tests.test_swarm_lifecycle import LifeCase, epoch


class Cutoffs(LifeCase):
    def setUp(self):
        super().setUp()
        self.clock.t = epoch("2026-09-28T13:29:00Z")
        self.state = self.root / "data"
        self.state.mkdir()
        self.receipt = {"pid": 123, "start": "456", "pgid": 123, "args": ["--stages", "1,2"]}
        bc.bl.write_json(self.state / "data_box.json", {"box_id": "sb_owned"})
        bc.bl.write_json(self.state / "completion-config.json", {"enabled": True})
        bc.bl.write_json(self.state / "completion-process.json", {"box": "sb_owned", "process": self.receipt,
                                                               "observed_at": self.clock(), "resume_args": "--stages 1,2"})
        self.current = copy.deepcopy(self.receipt)
        self.unreadable = False
        self.stops = []
        self.sleeps = []
        self.fail_sleep = False
        self.status = "running"
        test = self
        class API:
            def get(self, box):
                test.assertEqual(box, "sb_owned")
                return {"status": test.status, "vcpu_count": 8, "memory_mib": 32768, "state_disk_size_gib": 256}
            def sleep(self, box):
                test.sleeps.append(box)
                if test.fail_sleep:
                    raise TimeoutError("sleep response lost")
                test.status = "sleeping"
            def resume(self, box):
                test.fail("cutoff must never wake a box")
        class Handle:
            def __init__(self, api, box):
                pass
            def backfill_receipt(self):
                if test.unreadable:
                    raise RuntimeError("process receipt unreadable")
                return test.current
            def stop_backfill(self, *, expected):
                test.assertEqual(expected, test.current)
                test.stops.append(expected)
                test.current = None
        class Lease:
            def __init__(self, *args):
                self.stop = threading.Event()
                self.worker = None
                self.token = "owned-token"
                self.preserve_for_sleep = False
            def __enter__(self):
                return self
            def check(self):
                pass
            def __exit__(self, *args):
                pass
        self.api = API()
        self.lease = Lease
        patcher = mock.patch.object(bc, "BoxHandle", Handle)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cutoff = bc.Cutoff(self.state, self.store, self.cfg, api=self.api, clock=self.clock, lease=Lease)
        self.assertEqual(self.cutoff.tick()["status"], "tracking")
        self.clock.t = epoch("2026-09-28T13:30:30Z")
        self.good()
        self.budget.refresh()

    def test_overdue_owned_work_stops_and_sleeps_with_resume_intent_retained(self):
        result = self.cutoff.tick()
        self.assertEqual(result["status"], "cleaned")
        self.assertEqual(self.stops, [self.receipt])
        self.assertEqual(self.sleeps, ["sb_owned"])
        self.assertEqual(result["resume_args"], "--stages 1,2")
        self.assertIn("cannot resume", result["resume_deferred"])
        self.assertEqual(self.budget.status()["held_usd"], 0)
        self.assertAlmostEqual(self.budget.status()["actual_usd"], .005)
        self.cutoff.tick()
        self.assertEqual(len(self.sleeps), 1)

    def test_a_new_process_owner_is_not_stopped_or_slept_and_liability_stays(self):
        self.current = {**self.receipt, "start": "457"}
        result = self.cutoff.tick()
        self.assertIn("new owner", result["error"])
        self.assertEqual((self.stops, self.sleeps), ([], []))
        self.assertGreaterEqual(self.budget.status()["held_usd"], .39)
        self.clock.advance(2401)
        self.cutoff.tick()
        self.assertGreaterEqual(self.budget.status()["held_usd"], .39)
        self.assertGreater(self.budget.status()["actual_usd"], .4)

    def test_unreadable_process_identity_retains_hold_without_mutation(self):
        self.unreadable = True
        result = self.cutoff.tick()
        self.assertIn("unreadable", result["error"])
        self.assertEqual((self.stops, self.sleeps), ([], []))
        self.assertGreater(self.budget.status()["held_usd"], 0)

    def test_other_controller_lease_prevents_cleanup(self):
        class OtherOwner(self.lease):
            def __enter__(self):
                raise RuntimeError("another controller owns the operation")
        self.cutoff.lease = OtherOwner
        result = self.cutoff.tick()
        self.assertIn("another controller", result["error"])
        self.assertEqual((self.stops, self.sleeps), ([], []))
        self.assertGreater(self.budget.status()["held_usd"], 0)

    def test_unknown_sleep_keeps_hold_and_restart_honors_lease_expiry(self):
        self.fail_sleep = True
        result = self.cutoff.tick()
        self.assertEqual(result["status"], "cleanup_pending")
        self.assertGreater(self.budget.status()["held_usd"], 0)
        self.clock.advance(60)
        restarted = bc.Cutoff(self.state, self.store, self.cfg, api=self.api, clock=self.clock, lease=self.lease)
        restarted.tick()
        self.assertEqual(len(self.sleeps), 1)
        self.clock.t = result["retry_not_before"] + 1
        self.status = "sleeping"
        self.assertEqual(restarted.tick()["status"], "cleaned")
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_missing_preboundary_receipt_cannot_authorize_a_new_owner_after_boundary(self):
        self.store.put("completion_cutoff", {})
        (self.state / "completion-process.json").unlink()
        result = self.cutoff.tick()
        self.assertEqual(result["status"], "unowned")
        self.assertEqual((self.stops, self.sleeps), ([], []))

    def test_restart_can_recover_a_preboundary_receipt_without_admitting_new_work(self):
        self.store.put("completion_cutoff", {})
        self.store._exec("DELETE FROM sail_commitments")
        self.store.add_spend("sail_model", 100)  # new paid work is unaffordable; cleanup must still stop old work
        result = self.cutoff.tick()
        self.assertEqual(result["status"], "cleaned")
        self.assertEqual(self.stops, [self.receipt])
        self.assertEqual(self.sleeps, ["sb_owned"])
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_a_receipt_created_after_the_boundary_does_not_authorize_adoption(self):
        self.store.put("completion_cutoff", {})
        row = bc.bl.read_json(self.state / "completion-process.json")
        row["observed_at"] = self.clock()
        bc.bl.write_json(self.state / "completion-process.json", row)
        self.assertEqual(self.cutoff.tick()["status"], "unowned")
        self.assertEqual((self.stops, self.sleeps), ([], []))

    def test_a_new_cutoff_observer_never_wakes_an_already_sleeping_box(self):
        self.status = "sleeping"
        self.assertEqual(self.cutoff.tick()["status"], "cleaned")
        self.assertEqual((self.stops, self.sleeps), ([], []))

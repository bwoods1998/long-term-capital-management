"""Lifecycle admissions use real SQLite transactions, fake clocks and no paid services."""
import concurrent.futures
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import unittest

from league.swarm import settings
from league.swarm.guard import SailGuard
from league.swarm.lifecycle import BoundedClient, BudgetDeferred, SailBudget, capacity
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock


def epoch(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class LifeCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock(epoch("2026-09-29T00:00:00Z"))
        self.cfg = copy.deepcopy(settings.DEFAULTS)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.budget = SailBudget(self.store, self.cfg, clock=self.clock)
        self.good()
        self.budget.refresh()

    def good(self):
        self.store.put("guard", {"braked": False, "last_ok": self.clock(), "last": {"balance": 1000}})

    def family(self, fid):
        return self.store.add_family({"id": fid, "mechanism": "Synthetic test mechanism for " + fid, "structure": "debit_vertical",
                                      "roots": ["SPY"], "dte": [0, 2]}, origin="test")


class Periods(LifeCase):
    def test_monday_burst_spend_does_not_consume_prorated_period_and_restart_cannot_reset_it(self):
        self.clock.t = epoch("2026-09-28T12:00:00Z")
        guard = SailGuard(self.store, self.cfg, lambda: (1000, 0), clock=self.clock, disk_free=lambda: 100*2**30)
        self.store.add_spend("sail_model", 20)
        self.assertFalse(guard.check()["braked"])
        self.clock.t = epoch("2026-09-28T13:30:00Z")
        self.budget.refresh()
        self.assertFalse(guard.check()["braked"])
        self.assertEqual(self.budget.period()["cap"], 5.25)
        self.budget.reserve("monday", 2, kind="sail_model")
        self.budget.charge("monday", 2, final=True)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        restarted = SailBudget(other, self.cfg)
        self.assertEqual(restarted.status()["actual_usd"], 2)
        self.cfg["guard"]["burst_until"] = "2026-10-28T13:30:00Z"
        self.assertFalse(restarted.burst())
        with self.assertRaises(BudgetDeferred):
            restarted.reserve("cannot-borrow-tuesday", 2, kind="sail_model")

    def test_full_meter_fall_across_boundary_is_conservatively_charged_to_new_period(self):
        self.clock.t = epoch("2026-09-28T13:29:00Z")
        self.budget.meter(100)
        self.clock.advance(120)
        self.budget.meter(98)
        self.assertEqual(self.budget.status()["metered_usd"], 2)
        self.budget.meter(110)  # top-up never erases recorded spend
        self.assertEqual(self.budget.status()["metered_usd"], 2)

    def test_unknown_burst_call_carries_to_tuesday_until_confirmed_settlement(self):
        self.clock.t = epoch("2026-09-28T13:29:00Z")
        self.budget.reserve("late", 4, kind="sail_model")
        self.clock.t = epoch("2026-09-29T06:00:00Z")
        self.good()
        self.budget.refresh()
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("night", 3.65, kind="data_box", bucket="nightly")
        self.budget.charge("late", .01, final=True)
        self.budget.reserve("night", 3.65, kind="data_box", bucket="nightly")
        self.assertEqual(self.budget.status()["actual_usd"], .01)

    def test_burst_keeps_existing_admission_behavior(self):
        self.clock.t = epoch("2026-09-26T12:00:00Z")
        self.store.put("guard", {"braked": True})
        self.budget.reserve("tracked-but-existing-guard-still-owns-burst", 400, kind="gym_box")
        self.assertEqual(self.budget.status()["held_usd"], 400)

    def test_monday_protects_only_jobs_due_before_midnight_and_tuesday_starts_protected(self):
        self.clock.t = epoch("2026-09-28T13:30:00Z")
        self.good()
        self.budget.refresh()
        status = self.budget.status()
        self.assertEqual(status["protected"], {"nightly": 0, "forward": 0, "architect": 1})
        self.assertAlmostEqual(status["research_room_usd"], 2.28125)
        self.budget.reserve("monday-research", status["research_room_usd"], kind="sail_model")
        self.budget.charge("monday-research", status["research_room_usd"], final=True)
        self.clock.t = epoch("2026-09-29T00:00:00Z")
        self.good()
        self.budget.refresh()
        self.assertEqual(self.budget.status()["protected"], {"nightly": 3.65, "forward": 1.25, "architect": 1})


class Admissions(LifeCase):
    def test_elapsed_metered_house_use_does_not_consume_its_future_reservation_twice(self):
        self.budget.meter(100)
        room = self.budget.status()["research_room_usd"]
        self.budget.reserve("research", room, kind="sail_model")
        self.budget.charge("research", room, final=True)
        self.clock.advance(6*3600)
        self.good()
        self.budget.meter(100 - room - 1)  # Six hours of the already protected $4 House day.
        self.budget.reserve("night", 3.65, kind="data_box", bucket="nightly")
        self.budget.reserve("forward", 1.25, kind="gym_box", bucket="forward")
        self.budget.reserve("architect", 1, kind="sail_model", bucket="architect")
        self.assertAlmostEqual(self.budget.status()["used_usd"], 12)

    def test_a_later_confirmed_charge_cannot_disappear_after_settlement(self):
        self.budget.reserve("late-adjustment", .5, kind="gym_box")
        self.budget.charge("late-adjustment", .1, final=True)
        self.budget.charge("late-adjustment", .2)
        self.budget.charge("late-adjustment", .15)
        self.assertAlmostEqual(self.budget.status()["actual_usd"], .2)
        self.assertEqual(self.budget.status()["held_usd"], 0)

    def test_two_connections_cannot_each_take_the_last_research_dollar(self):
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        second = SailBudget(other, self.cfg)
        start = threading.Barrier(2)
        def admit(pair):
            key, budget = pair
            start.wait()
            try:
                budget.reserve(key, 1, kind="sail_model")
                return True
            except BudgetDeferred:
                return False
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            self.assertEqual(sorted(ex.map(admit, [("a", self.budget), ("b", second)])), [False, True])
        self.assertEqual(self.budget.status()["held_usd"], 1)

    def test_midnight_research_cannot_take_tuesdays_maintenance_reservations(self):
        room = self.budget.status()["research_room_usd"]
        self.assertAlmostEqual(room, 1.6)
        self.budget.reserve("research", room, kind="sail_model")
        self.budget.charge("research", room, final=True)
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("extra", .01, kind="gym_box")
        self.clock.advance(6*3600)
        self.good()
        self.budget.reserve("night", 3.65, kind="data_box", bucket="nightly")
        self.budget.reserve("forward", 1.25, kind="gym_box", bucket="forward")
        self.budget.reserve("architect", 1, kind="sail_model", bucket="architect")
        self.assertAlmostEqual(self.budget.status()["used_usd"], 12)

    def test_unknown_dispatch_keeps_hold_known_refusal_can_release_and_readmit(self):
        self.budget.reserve("uncertain", 1, kind="sail_model")
        self.assertEqual(self.budget.reserve("uncertain", 1, kind="sail_model")["state"], "open")
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("other", 1, kind="sail_model")
        self.budget.charge("uncertain", 0, final=True, released=True)
        self.budget.reserve("other", 1, kind="sail_model")
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("uncertain", 1, kind="sail_model")

    def test_safety_and_bad_maintenance_config_defer_even_reserved_priority(self):
        self.store.put("guard", {"braked": True, "last_ok": self.clock()})
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("night", 1, kind="data_box", bucket="nightly")
        self.good()
        self.cfg["lifecycle"]["maintenance_usd"]["nightly"] = float("nan")
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("night", 1, kind="data_box", bucket="nightly")

    def test_meter_and_untagged_old_costs_still_reduce_room(self):
        self.store.add_spend("gym_box", 2)
        self.assertEqual(self.budget.status()["research_room_usd"], 0)
        self.budget.meter(100)
        self.budget.meter(90)
        with self.assertRaises(BudgetDeferred):
            self.budget.reserve("night", 1, kind="data_box", bucket="nightly")


class Evidence(LifeCase):
    def prepare(self, pnl=-1):
        (self.root / "data").mkdir()
        (self.root / "data/calendar.json").write_text(json.dumps({"exceptions": {}}))
        self.family("family")
        version = self.store.add_version("family", "def decide(state, quotes):\n    return []\n", {}, author="test")
        n = version["n"]
        self.store.set_band("family", "candidate", reason="test")
        ready = {"day": "2026-09-28", "gate_checkpoint": "sbcp_test"}
        self.cfg["forward"].update(ready=ready, current_bundle="bundle")
        self.cfg["gym"]["gate_checkpoint"] = "sbcp_test"
        self.store.set_state("family", banded_version=n, forward_replay={"target": {"day": ready["day"], "checkpoint": "sbcp_test", "bundle": "bundle"}, "version": n})
        for i, day in enumerate(("2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28")):
            self.store.add_forward("family", "nightly", [{"id": str(i*4+j), "day": day, "pnl": pnl, "max_loss": 100} for j in range(4)], version=n)
        return n

    def test_flat_negative_and_insufficient_are_distinct_and_stale_cannot_lift_floor(self):
        self.assertEqual(self.budget.refresh()["evidence"]["status"], "insufficient")
        self.prepare(0)
        state = self.budget.refresh()
        self.assertEqual((state["mode"], state["evidence"]["status"]), ("floor", "flat"))
        self.cfg["forward"]["current_bundle"] = "new-bundle"
        state = self.budget.refresh()
        self.assertEqual((state["mode"], state["evidence"]["status"]), ("floor", "insufficient"))

    def test_real_source_wins_and_retired_negative_rows_are_not_erased(self):
        n = self.prepare(100)
        for i, day in enumerate(("2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28")):
            self.store.add_forward("family", "real", [{"id": str(i*4+j), "day": day, "pnl": -1, "max_loss": 100} for j in range(4)], version=n)
        out = self.budget.refresh()
        self.assertEqual((out["mode"], out["evidence"]["observations"]), ("floor", 20))
        self.store.retire("family", "test")
        self.assertEqual(self.budget.refresh()["evidence"]["observations"], 20)

    def test_legacy_empty_source_is_not_compute_evidence(self):
        self.prepare(1)
        self.store._exec("UPDATE forward SET source=''")
        self.assertEqual(self.budget.refresh()["evidence"]["status"], "insufficient")

    def test_missing_version_is_not_silently_dropped_from_compute_evidence(self):
        self.prepare(1)
        self.store.add_forward("family", "real", [{"id": "unknown-loss", "day": "2026-09-28", "pnl": -1000, "max_loss": 100}])
        self.assertEqual(self.budget.refresh()["evidence"]["status"], "insufficient")

    def test_retired_positive_rows_cannot_lift_floor_through_a_new_zero_trade_family(self):
        self.prepare(1)
        prior = self.store.family("family")["state"]
        self.store.retire("family", "test")
        self.family("new")
        n = self.store.add_version("new", "def decide(state, quotes):\n    return []\n", {}, author="test")["n"]
        self.store.set_band("new", "candidate", reason="test")
        self.store.set_state("new", banded_version=n, forward_replay={**prior["forward_replay"], "version": n})
        self.store.put("lifecycle", {"mode": "floor"})
        result = self.budget.refresh()
        self.assertEqual((result["mode"], result["evidence"]["status"]), ("floor", "insufficient"))

    def test_retired_positive_history_without_delivery_cannot_lift_floor(self):
        self.prepare(1)
        self.store.put("lifecycle", {"mode": "floor"})
        self.store.retire("family", "test")
        self.cfg["forward"].pop("ready")
        self.cfg["forward"].pop("current_bundle")
        result = self.budget.refresh()
        self.assertEqual(result["mode"], "floor")
        self.assertEqual(result["evidence"]["status"], "insufficient")

    def test_successful_zero_trade_replay_does_not_invent_flat_observations(self):
        self.prepare()
        self.store._exec("DELETE FROM forward")
        out = self.budget.refresh()
        self.assertEqual(out["evidence"]["status"], "insufficient")
        self.assertEqual(out["evidence"]["observations"], 0)

    def test_cohort_turnover_keeps_all_family_identity_and_live_ownership_state(self):
        for i in range(20):
            self.family(f"family-{i:02}")
        self.store.set_state("family-19", banded_version=1, live_promoted_at=123, open_tuition="owned")
        self.store.set_band("family-19", "probe", reason="test")
        before = self.store.family("family-19")
        cohort = self.budget.refresh()["cohort"]
        self.assertEqual(len(cohort), 16)
        self.store.retire(cohort[0], "test")
        next_cohort = self.budget.refresh()["cohort"]
        self.assertEqual(len(next_cohort), 16)
        self.assertNotIn(cohort[0], next_cohort)
        self.assertEqual(self.store.family("family-19"), before)
        self.assertEqual(len(self.store.families()), 20)


class Bounds(unittest.TestCase):
    def test_capacity_is_an_actual_resource_check(self):
        good = {"vcpu_count": 8, "memory_mib": 32768, "state_disk_size_gib": 256}
        self.assertAlmostEqual(capacity(good)["capacity_usd_hour"], .5547744)
        for bad in ({}, {**good, "vcpu_count": 9}, {**good, "memory_mib": True}, {**good, "state_disk_size_gib": 300}):
            with self.assertRaises(BudgetDeferred):
                capacity(bad)

    def test_remote_timeout_and_http_deadline_are_both_bounded(self):
        calls = []
        class API:
            def exec(self, *args, **kwargs):
                calls.append((args, kwargs))
        clock = Clock(100)
        api = BoundedClient(API(), lambda: 300, clock=clock)
        api.exec("owned", ["python", "job.py"], timeout=600)
        self.assertEqual(calls[0][1]["timeout"], 80)
        self.assertIn("timeout --signal=TERM --kill-after=10 70", calls[0][0][1])
        clock.t = 299
        with self.assertRaises(BudgetDeferred):
            api.exec("owned", "job")
        self.assertEqual(len(calls), 1)

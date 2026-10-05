"""Synthetic model-only admission boundaries; no real rates or native authority.

Only temporary SQLite and injected response transports are used. The full model
charge evidence remains a fabricated fixture, including fees, taxes and accepted
liability coverage; these passes cannot supply those facts for an actual account.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest

from league.swarm.daily_compute import DailyAdmissionError, DailyBudget, STATE_KEY
from league.swarm.research_transport import ModelCapability, ResearchCapabilityError
from league.swarm.store import SwarmStore
from league.tests import test_daily_compute_budget as daily_fixtures
from league.tests import test_research_transport as broker_fixtures
from league.tests import test_sail_research_host as sail_fixtures


class ModelOnlyDailyAdmission(unittest.TestCase):
    def setUp(self):
        self.f = daily_fixtures.DailyComputeBudget("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.short = replace(self.f.tariff, valid_from=self.f.clock()-1,
                             valid_until=self.f.clock()+60,
                             provenance="SYNTHETIC part-day compute evidence; not a model tariff")
        self.budget = self.f.make_budget(tariff=self.short)

    def test_model_only_initialize_still_books_complete_prior_cost(self):
        with tempfile.TemporaryDirectory() as root:
            store = SwarmStore(Path(root), clock=self.f.clock)
            try:
                budget = self.f.make_budget(store=store, tariff=self.short)
                budget.initialize(replace(self.f.prior, upper_usd="3.5"))
                self.assertEqual(budget.summary()["prior_cost_upper_nanos"], 3_500_000_000)
                budget.reserve_inference("model", "21.5", provenance="SYNTHETIC inclusive model maximum")
                self.assertEqual(budget.summary()["total_upper_nanos"], 25_000_000_000)
                with self.assertRaises(DailyAdmissionError):
                    budget.reserve_inference("excess", "0.000000001", provenance="SYNTHETIC maximum")
                with self.assertRaises(DailyAdmissionError):
                    budget.initialize(self.f.prior)
            finally:
                store.close()

    def test_exact_25_model_cap_refuses_next_nanodollar(self):
        self.budget.reserve_inference("model", "25", provenance="SYNTHETIC inclusive model maximum")
        self.budget.dispatch("model")
        self.assertEqual(self.budget.summary()["total_upper_nanos"], 25_000_000_000)
        before = self.budget._load()
        with self.assertRaises(DailyAdmissionError):
            self.budget.reserve_inference("extra", "0.000000001", provenance="SYNTHETIC maximum")
        self.assertEqual(self.budget._load(), before)

    def test_pending_model_hold_survives_restart_and_utc_rollover(self):
        self.budget.reserve_inference("original", "12", provenance="SYNTHETIC inclusive accepted liability")
        self.budget.dispatch("original")
        original = self.budget._load()["inference"]["original"]
        self.f.clock.advance(86400)
        restarted = self.f.make_budget(tariff=self.short)
        self.assertEqual(restarted.summary()["inference_upper_nanos"], 12_000_000_000)
        self.assertEqual(restarted._load()["inference"]["original"], original)
        with self.assertRaises(DailyAdmissionError):
            restarted.dispatch("original")
        with self.assertRaises(DailyAdmissionError):
            restarted.cancel_unsent("original")

    def test_initial_resource_admission_cannot_use_model_only_branch(self):
        before = self.budget._load()
        with self.assertRaisesRegex(DailyAdmissionError, "day tariff"):
            self.budget.reserve_resource("first-gym", self.f.gym)
        self.assertEqual(self.budget._load(), before)

    def test_every_original_resource_history_keeps_compute_gate(self):
        for status in ("reserved", "pending-create", "running", "terminal", "canceled", "volume"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                store = SwarmStore(Path(root), clock=self.f.clock)
                try:
                    full = self.f.make_budget(store=store)
                    full.initialize(self.f.prior)
                    bound = self.f.controller
                    if status == "volume":
                        from league.swarm.daily_compute import ResourceBound
                        bound = ResourceBound("synthetic-volume", "volume", 0, "0", "0", "1", "0",
                                              "SYNTHETIC persistent storage capacity")
                    full.reserve_resource("original", bound)
                    if status == "canceled":
                        full.cancel_unsent("original")
                    elif status not in ("reserved",):
                        full.dispatch("original")
                        if status != "pending-create":
                            full.attach("original", "synthetic-resource", created_at=self.f.clock(),
                                        observed_bound=bound, provenance="SYNTHETIC original GET")
                            if status == "terminal":
                                full.terminal_observed("original", "synthetic-resource", observed_at=self.f.clock(),
                                                       status="terminated", provenance="SYNTHETIC original terminal GET")
                    narrow = self.f.make_budget(store=store, tariff=self.short)
                    before = narrow._load()
                    with self.assertRaisesRegex(DailyAdmissionError, "full UTC day"):
                        narrow.reserve_inference("new-model", "0.1", provenance="SYNTHETIC inclusive model maximum")
                    self.assertEqual(narrow._load(), before)
                finally:
                    store.close()

    def test_unknown_incomplete_shared_or_uncovered_inventory_still_refuses(self):
        for change in ({"unknown_obligations": True}, {"complete": False}, {"exclusive_writer": False},
                       {"resource_ids": ("unpriced-old-resource",)}, {"model_keys": ("unpriced-old-model",)},
                       {"valid_until": self.f.clock()-1}):
            with self.subTest(change=change), self.assertRaises(DailyAdmissionError):
                self.f.make_budget(tariff=self.short, inventory=replace(self.f.inventory, **change)).reserve_inference(
                    "new-model", "0.1", provenance="SYNTHETIC inclusive model maximum")
        self.assertEqual(self.budget._load()["inference"], {})

    def test_original_scope_cache_and_breach_checks_still_refuse(self):
        self.budget.reserve_inference("model", "1", provenance="SYNTHETIC maximum")
        self.budget.dispatch("model")
        with self.assertRaises(DailyAdmissionError):
            self.budget.settle_inference("model", accrued_day="2026-10-04", actual_usd="1.01",
                                         provenance="SYNTHETIC original final invoice exceeding ceiling")
        with self.assertRaises(DailyAdmissionError):
            self.budget.summary()
        self.assertTrue(self.budget._load()["breached"])


class ModelOnlySailAdmission(unittest.TestCase):
    def setUp(self):
        self.f = sail_fixtures.SailResearchHost("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.short = replace(self.f.f.tariff, valid_from=self.f.f.now-1,
                             valid_until=self.f.f.now+60,
                             provenance="SYNTHETIC compute interval only")
        self.f.bill_file = self.f.rewrite("short-billing.json", {**self.f.billing, "tariff": asdict(self.short)})

    def test_actual_bridge_constructor_and_broker_send_accept_model_only(self):
        self.f.adapters = self.f.build()
        self.f.budget = DailyBudget(self.f.store, self.short, self.f.f.inventory)
        self.f.broker = self.f.make_broker()
        result = self.f.model_call("short-compute-model")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.f.posts("/v1/responses")), 1)
        self.assertEqual(self.f.posts("/sailboxes/from_checkpoint"), [])
        self.assertEqual(self.f.budget._load()["resources"], {})
        self.assertGreater(self.f.budget.summary()["inference_upper_nanos"], 0)
        self.assertEqual(len(self.f.budget._load()["inference"]), 1)

    def test_bridge_retains_pending_model_ceiling_after_unknown_bill(self):
        self.f.adapters = self.f.build()
        self.f.budget = DailyBudget(self.f.store, self.short, self.f.f.inventory)
        self.f.broker = self.f.make_broker()
        result = self.f.model_call("unknown-original")
        hold = self.f.budget._load()["inference"]
        self.assertIsNone(next(iter(hold.values()))["receipt"])
        self.assertGreater(next(iter(hold.values()))["max_nanos"], 0)
        self.assertEqual(self.f.model_call("unknown-original"), result)
        self.assertEqual(len(self.f.posts("/v1/responses")), 1)
        self.assertEqual(self.f.budget._load()["inference"], hold)

    def test_bridge_constructor_refuses_retained_canceled_resource_row(self):
        self.f.budget.reserve_resource("old-resource", self.f.f.bound)
        self.f.budget.cancel_unsent("old-resource")
        with self.assertRaisesRegex(ResearchCapabilityError, "resource history"):
            self.f.build()
        self.assertEqual(self.f.transport.calls, [])

    def test_bridge_constructor_refuses_retained_pending_create_row(self):
        self.f.budget.reserve_resource("old-resource", self.f.f.bound)
        self.f.budget.dispatch("old-resource")
        with self.assertRaisesRegex(ResearchCapabilityError, "resource history"):
            self.f.build()
        self.assertEqual(self.f.transport.calls, [])

    def test_bridge_never_classifies_corrupt_original_cache_as_model_only(self):
        original = self.f.budget._load()
        self.f.store.put(STATE_KEY, {**original, "resources": {"invented": {}}})
        with self.assertRaisesRegex(DailyAdmissionError, "immutable history"):
            self.f.build()
        self.assertEqual(self.f.transport.calls, [])

    def test_bridge_model_only_still_requires_fee_tax_and_accepted_coverage(self):
        for field in ("inclusive_fees_taxes", "ongoing_liability_covered"):
            self.f.bill_file = self.f.rewrite("missing-"+field+".json", {
                **self.f.billing, "tariff": asdict(self.short),
                "agreement": {**self.f.billing["agreement"], field: False}})
            with self.subTest(field=field), self.assertRaises(ResearchCapabilityError):
                self.f.build()
        self.assertEqual(self.f.transport.calls, [])

    def test_bridge_model_only_still_refuses_current_price_as_guarantee(self):
        self.f.bill_file = self.f.rewrite("observed-only.json", {
            **self.f.billing, "tariff": asdict(self.short),
            "agreement": {**self.f.billing["agreement"], "kind": "current_documented_rate"}})
        with self.assertRaises(ResearchCapabilityError):
            self.f.build()
        self.assertEqual(self.f.transport.calls, [])


class ModelOnlyBrokerPolicy(unittest.TestCase):
    def setUp(self):
        self.f = broker_fixtures.ResearchTransport("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.short = replace(self.f.tariff, valid_from=self.f.clock()-1, valid_until=self.f.clock()+60)
        self.budget = DailyBudget(self.f.store, self.short, self.f.inventory)

    def test_expired_model_policy_still_refuses_before_any_dispatch(self):
        policy = replace(self.f.model_policy, valid_until=self.f.clock())
        broker = self.f.make_broker(budget=self.budget, capability=ModelCapability(policy, self.f.tokens, self.f.send))
        with self.assertRaisesRegex(ResearchCapabilityError, "price evidence"):
            self.f.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "expired"}, broker=broker)
        self.assertEqual(self.f.model_calls, [])
        self.assertEqual(self.budget._load()["inference"], {})

    def test_model_output_quantity_bound_still_refuses_before_dispatch(self):
        broker = self.f.make_broker(budget=self.budget)
        with self.assertRaisesRegex(ResearchCapabilityError, "host policy"):
            self.f.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}],
                                     "key": "too-many-output", "max_output": self.f.model_policy.max_output_tokens+1}, broker=broker)
        self.assertEqual(self.f.model_calls, [])
        self.assertEqual(self.budget._load()["inference"], {})

    def test_model_full_payload_count_still_refuses_before_dispatch(self):
        capability = ModelCapability(self.f.model_policy, lambda body: self.f.model_policy.max_input_tokens+1, self.f.send)
        broker = self.f.make_broker(budget=self.budget, capability=capability)
        with self.assertRaisesRegex(ResearchCapabilityError, "full model payload"):
            self.f.call("evaluate", {"profile": "reviewed", "items": [{"role": "user", "content": "x"}], "key": "too-large-input"}, broker=broker)
        self.assertEqual(self.f.model_calls, [])
        self.assertEqual(self.budget._load()["inference"], {})


if __name__ == "__main__":
    unittest.main()

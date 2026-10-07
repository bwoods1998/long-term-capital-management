"""Fabricated ordinary-service facts through real host/bridge/broker admission.

All account, rate, source-document, isolation and cost facts are synthetic. Tests
make no native/provider/key calls and provide no startup or final-bill authority.
"""
from dataclasses import asdict, replace
from decimal import Decimal
import datetime as dt
import hashlib
import json
import os
import time
import unittest
from unittest import mock

from ltcm.provider import PROFILES as STOCK
from league.swarm import research_host as host
from league.swarm import daily_compute as daily
from league.swarm.sail_research_host import SailBridgeInputs, _Bridge, build_sail_host_adapters
from league.swarm.self_service_cost import CostBasisError, PROFILES, read_cost_basis
from league.swarm.research_transport import (ResearchBroker, ModelPolicy, IsolationProof,
                                            ISOLATION_FACTS, NAMESPACE_FACTS, ResearchCapabilityError)
from league.swarm.store import SwarmStore
from league.tests import test_research_host as host_fixture
from league.tests.test_sail_research_host import SailFixture
from league.tests.test_research_transport import PRODUCTION


class SelfServiceAdmission(unittest.TestCase):
    def setUp(self):
        self.f = host_fixture.ResearchHost("runTest")
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f
        f.bound = daily.ResourceBound("synthetic-S", "gym", 1, "16", "32", "0", "0.005",
                                      "SYNTHETIC source-enforced dimensions and known fee")
        f.policy = replace(f.policy, resource_bound=f.bound)
        self.app = "app_aaaaaaaa-0000-0000-0000-000000000001"; self.image = "sha256:"+"a"*64
        self.transport = SailFixture(self)
        self.store = SwarmStore(f.broker_root); self.addCleanup(self.store.close)
        self.changes = {}; self.bill_sequence = 0
        quantity = {name: dict(f.manifest)[name] for name in (
            "league/swarm/sail_research_host.py", "league/swarm/research_transport.py",
            "league/swarm/self_service_cost.py", "ltcm/provider.py")}
        self.refs = {}
        for role, raw, url in (
            ("terms", b"SYNTHETIC prospective rates; taxes excluded; no price lock", "https://www.sailresearch.com/terms"),
            ("pricing", b"SYNTHETIC original four profile and native price observations", "https://docs.sailresearch.com/pricing"),
            ("quantity_source", json.dumps(quantity).encode(), "host:source-enforced-quantities"),
            ("account_facts", b"SYNTHETIC complete exclusive plan/region/prior/fees/tax/pending facts", "host:synthetic-account-facts")):
            ref = f.file(role+".txt", raw)
            self.refs[role] = {"path": str(ref.path), "sha256": ref.sha256, "url": url}
        self.initial_basis = self.basis()
        self.models = {"schema": 2, "scope": f.policy.scope, "profiles": {}, "cost_basis": self.initial_basis,
                       "provenance": "SYNTHETIC local observed-price admission, no provider-bill guarantee"}
        for name in PROFILES:
            model, window, inp, _, out = STOCK[name]
            p = ModelPolicy(model, inp, out, "0", 1048576, 32000, f.now-10, f.now+86400,
                            "SYNTHETIC source quantity policy at observed prices; no future rate lock", timeout_seconds=30)
            self.models["profiles"][name] = {"policy": asdict(p), "max_request_bytes": 1000000,
                                          "billable_input_ceiling": 1048576, "completion_window": window}
        self.model_file = f.file("models-schema2.json", json.dumps(self.models).encode())
        self.cp = {"schema": 1, "scope": f.policy.scope, "checkpoint_id": f.policy.checkpoint,
                   "source_sailbox_id": PRODUCTION, "app_id": self.app, "image_id": self.image,
                   "source_checkpoint_generation": 3, "resource_bound": asdict(f.bound),
                   "gym_bundle": f.policy.gym_bundle, "gym_execution": f.policy.execution,
                   "store_root": "/data/approved-train-validation", "remote_root": "/workspace/isolated-fixture",
                   "python": "python3", "train_validation_only": True, "guest_credentials_absent": True,
                   "no_live_processes": True, "no_network": True, "provenance": "SYNTHETIC clean checkpoint"}
        self.cp_file = f.file("checkpoint.json", json.dumps(self.cp).encode())
        tariff = self.parsed(self.initial_basis).tariff_document()
        self.config = replace(f.config, research_policy=f.policy, tariff=daily.tariff_from_document(tariff))
        f.config = self.config
        self.inputs = SailBridgeInputs(self.cp_file, self.model_file, self.billing, f.context,
                                       lambda *_: None, lambda *_: None)
        self.adapters = self.build()
        self.budget = daily.DailyBudget(self.store, self.adapters.billing()[0], self.config.inventory)
        self.broker = self.broker_for()

    def basis(self):
        now = time.time()
        # These are fabricated source-bound quantity projections, never real invoices.
        pending = []
        state = daily.DailyBudget(self.store, self.f.tariff, self.f.inventory)._load()
        for key, row in state["inference"].items():
            if row["dispatch_at"] is not None and not row["canceled"] and row["receipt"] is None:
                pending.append({"key": key, "upper_usd": daily._usd(row["max_nanos"]), "provenance": "SYNTHETIC known original projection"})
        for key, row in state["resources"].items():
            if row["dispatch_at"] is not None and not row["canceled"] and row["terminal_at"] is None:
                pending.append({"key": key, "upper_usd": "4", "provenance": "SYNTHETIC known original capacity projection"})
        value = {"schema": 2, "mode": "observed_self_service", "scope": self.f.policy.scope,
                 "observed_at": now-1, "refresh_by": now+120, "future_rate_lock": False, "references": self.refs,
                 "applicability": {"plan": "SYNTHETIC Free", "region": "SYNTHETIC non-US-only", "provenance": "SYNTHETIC account facts"},
                 "model_rates": {name: {"input_usd_million": STOCK[name][2], "output_usd_million": STOCK[name][4],
                                        "fixed_request_usd": "0"} for name in PROFILES},
                 "resource_rates": {"vcpu_usd_hour": "0.015", "memory_gib_usd_hour": "0.008",
                                    "disk_gib_usd_hour": "0.0007", "volume_gib_usd_hour": "0.000411"},
                 "fees_taxes": {"fee_fraction_upper": "0", "tax_fraction_upper": "0", "fixed_day_fee_upper_usd": "0",
                                "creation_fee_upper_usd": "0.005", "provenance": "SYNTHETIC known zeros, no account claim"},
                 "prior": {"utc_day": dt.datetime.now(dt.timezone.utc).date().isoformat(), "upper_usd": "0",
                           "complete": True, "provenance": "SYNTHETIC complete prior costs"},
                 "pending": pending, "provenance": "SYNTHETIC ordinary-service factual basis"}
        value.update(self.changes)
        return value

    def parsed(self, value):
        return read_cost_basis(value, scope=self.f.policy.scope, now=time.time(),
            read_reference=lambda p, s: host.ReviewedFile(p, s).read(),
            quantity_sources=json.loads(host.ReviewedFile(__import__('pathlib').Path(self.refs["quantity_source"]["path"]),
                                                       self.refs["quantity_source"]["sha256"]).read()))

    def billing(self):
        self.bill_sequence += 1
        basis = self.basis()
        # Keep unknown document readable: admission fails in the real reader.
        try: tariff = self.parsed(basis).tariff_document()
        except CostBasisError: tariff = asdict(self.config.tariff)
        now = time.time()
        inventory = replace(self.config.inventory, observed_at=now-1, valid_until=now+120,
                            resource_ids=tuple(self.transport.rows),
                            model_keys=tuple(row["key"] for row in basis["pending"] if row["key"].startswith("model-")))
        value = {"schema": 2, "scope": self.f.policy.scope, "observed_at": now-1, "valid_until": now+120,
                 "tariff": tariff, "inventory": asdict(inventory), "cost_basis": basis, "provenance": "SYNTHETIC fresh original-scope facts"}
        return self.f.file("billing-"+str(self.bill_sequence)+".json", json.dumps(value).encode())

    def build(self):
        return build_sail_host_adapters(self.config, inputs=self.inputs,
            key_source=lambda: (_ for _ in ()).throw(AssertionError("credential access")),
            box_transport=self.transport, inference_transport=self.transport)

    def broker_for(self):
        def proof(peer, **kw):
            # Mirror the actual HostRuntime verifier's fresh shared billing step.
            self.budget.tariff, self.budget.inventory = self.adapters.billing()
            now = time.time()
            return IsolationProof(self.f.policy.scope, peer, os.getuid(), str(self.f.broker_root), kw["policy_digest"],
                "namespaces", now, now+60, self.f.runbook.sha256, "b"*64, "c"*64, self.f.adapter_file.sha256,
                tuple(sorted(ISOLATION_FACTS | NAMESPACE_FACTS)), "SYNTHETIC isolation only")
        return ResearchBroker(self.store, self.budget, self.f.policy, artifact_root=self.f.artifact,
            provider=self.adapters.provider, driver_factory=self.adapters.driver_factory,
            model_adapters=self.adapters.models, verify_isolation=proof)

    def call(self, key="observed-model", profile="flash41_asap"):
        self.broker.authorize_peer(os.getpid(), os.getuid(), os.getgid())
        return self.broker.evaluate(profile, [{"role": "user", "content": "fabricated text"}], key=key)

    def test_real_host_build_and_normal_model_send_use_observed_mode(self):
        runtime = host.HostRuntime(self.config, self.adapters)
        runtime._build_broker()
        self.addCleanup(runtime.store.close)
        self.assertIsInstance(runtime.budget.tariff, daily.ObservedTariffEvidence)
        self.assertEqual(set(runtime.broker._models), set(PROFILES))
        result = self.call()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(method == "POST" and path == "/v1/responses" for method,path,*_ in self.transport.calls), 1)
        tariff, inventory = self.adapters.billing()
        report = daily.DailyBudget(self.store, tariff, inventory).summary()
        self.assertTrue(report["within_cap"])
        self.assertFalse(report["verified_all_in_ceiling"])
        self.assertFalse(report["provider_final_bill_guaranteed"])
        self.assertIsNone(report["total_upper_usd"])
        self.assertGreater(Decimal(report["admission_total_at_observed_rates_usd"]), 0)

    def test_unknown_fees_tax_plan_prior_and_pending_refuse_before_post(self):
        baseline = self.basis()
        changes = ({"fees_taxes": {**baseline["fees_taxes"], "tax_fraction_upper": None}},
                   {"fees_taxes": {**baseline["fees_taxes"], "fee_fraction_upper": None}},
                   {"applicability": {**baseline["applicability"], "plan": None}},
                   {"prior": {**baseline["prior"], "upper_usd": None, "complete": False}},
                   {"pending": [{"key": "unknown-original", "upper_usd": None, "provenance": None}]})
        for change in changes:
            self.changes = change
            with self.subTest(change=change), self.assertRaises(CostBasisError): self.build()
        self.assertEqual(self.transport.calls, [])

    def test_model_rate_increase_cannot_use_old_policy_or_post(self):
        rates = self.basis()["model_rates"]
        rates["flash41_asap"]["input_usd_million"] = "0.16"
        self.changes = {"model_rates": rates}
        with self.assertRaisesRegex(CostBasisError, "exceed"): self.build()
        self.assertEqual(self.transport.calls, [])

    def test_extra_pending_charge_is_refused_instead_of_zeroed(self):
        self.changes = {"pending": [{"key": "foreign-original", "upper_usd": "10", "provenance": "SYNTHETIC old obligation"}]}
        with self.assertRaisesRegex(daily.DailyAdmissionError, "unbound pending"): self.build()

    def test_pending_hold_survives_restart_lower_quote_and_utc(self):
        self.call()
        state = self.budget._load(); key = next(iter(state["inference"]))
        basis = self.basis(); basis["pending"][0]["upper_usd"] = "5"
        tariff = daily.tariff_from_document(self.parsed(basis).tariff_document())
        budget = daily.DailyBudget(self.store, tariff, self.config.inventory)
        budget.reserve_inference("additional-unsent", "0.1", provenance="SYNTHETIC reserve after pending increase")
        later = replace(tariff, basis_sha256="b"*64, pending=((key, "0.1"),))
        restarted = daily.DailyBudget(self.store, later, self.config.inventory)
        self.assertGreaterEqual(restarted.summary()["inference_upper_nanos"], 5*daily.NANOS)
        tomorrow = (int(time.time()//86400)+1)*86400+1
        dated = replace(later, valid_from=tomorrow-1, valid_until=tomorrow+120,
                        prior_utc_day=dt.datetime.fromtimestamp(tomorrow,dt.timezone.utc).date().isoformat())
        inventory = replace(self.config.inventory, observed_at=tomorrow-1, valid_until=tomorrow+120)
        self.store.clock = lambda: tomorrow
        restarted = daily.DailyBudget(self.store, dated, inventory)
        self.assertGreaterEqual(restarted.summary()["inference_upper_nanos"], 5*daily.NANOS)

    def test_original_exact_25_next_nanodollar_and_nonzero_prior(self):
        tariff, inventory = self.adapters.billing()
        tariff = replace(tariff, prior_upper_usd="3.5")
        budget = daily.DailyBudget(self.store, tariff, inventory)
        budget.reserve_inference("exact25", "21.5", provenance="SYNTHETIC observed-price allocation")
        self.assertTrue(budget.summary()["within_cap"])
        with self.assertRaises(daily.DailyAdmissionError):
            budget.reserve_inference("next-nano", "0.000000001", provenance="SYNTHETIC exact boundary")

    def test_schema1_journal_is_unchanged_until_explicit_observed_admission(self):
        before = self.budget._load()
        self.assertNotIn("observed_basis", before)
        daily.DailyBudget(self.store, self.f.tariff, self.f.inventory).summary()
        self.call()
        self.assertIn("observed_basis", self.budget._load())
        with self.assertRaisesRegex(daily.DailyAdmissionError, "compatible accounting reader"):
            daily.DailyBudget(self.store, self.f.tariff, self.f.inventory).summary()

    def test_observed_native_resource_reserves_real_capacity_with_original_identity(self):
        self.broker.authorize_peer(os.getpid(), os.getuid(), os.getgid())
        self.broker._ensure_gym()
        state = self.budget._load()
        self.assertEqual(len(state["resources"]), 1)
        row = next(iter(state["resources"].values()))
        self.assertEqual(row["tariff"]["mode"], "observed_self_service")
        self.assertEqual(row["resource_id"], next(iter(self.transport.rows)))
        tariff, inventory = self.adapters.billing()
        report = daily.DailyBudget(self.store, tariff, inventory).summary()
        self.assertGreaterEqual(report["admission_total_at_observed_rates_nanos"], 3974600000)

    def test_current_rate_freshness_is_not_acceptance_timeout_guarantee(self):
        bridge = _Bridge(self.config, self.inputs, time.time, cleanup_only=True)
        tariff, _ = bridge.billing(initialization_preflight=True)
        self.assertFalse(tariff.covers_day(int(time.time()//86400)))
        basis = self.basis(); basis["future_rate_lock"] = True
        with self.assertRaises(CostBasisError): self.parsed(basis)

    def test_source_quantity_reference_and_raw_bytes_are_bound(self):
        changed = json.loads(json.dumps(self.basis()))
        ref = self.f.file("wrong-quantities.json", b"{}")
        changed["references"]["quantity_source"] = {"path": str(ref.path), "sha256": ref.sha256, "url": "host:wrong"}
        with self.assertRaisesRegex(CostBasisError, "actual reviewed artifact"):
            _Bridge(self.config, self.inputs, time.time, cleanup_only=True).read_basis(changed)

    def test_original_cache_and_durable_breach_still_refuse(self):
        self.call()
        key = next(iter(self.budget._load()["inference"]))
        with self.assertRaises(daily.DailyAdmissionError):
            self.budget.settle_inference(key, accrued_day=dt.datetime.now(dt.timezone.utc).date().isoformat(),
                actual_usd="10", provenance="SYNTHETIC original invoice exceeds admitted projection")
        self.assertTrue(self.budget._load()["breached"])
        with self.assertRaises(daily.DailyAdmissionError): self.build()

    def test_nonzero_known_fee_tax_and_day_cost_enter_actual_reservation(self):
        basis = self.basis()
        basis["fees_taxes"].update(fee_fraction_upper="0.1", tax_fraction_upper="0.2",
                                 fixed_day_fee_upper_usd="0.5", creation_fee_upper_usd="0")
        self.changes = {"fees_taxes": basis["fees_taxes"]}
        self.models["cost_basis"] = basis
        for row in self.models["profiles"].values():
            for name in ("input_usd_million", "output_usd_million"):
                row["policy"][name] = format(Decimal(row["policy"][name])*Decimal("1.32"), "f")
        self.model_file = self.f.file("models-adjusted.json", json.dumps(self.models).encode())
        self.inputs = replace(self.inputs, models=self.model_file)
        self.adapters = self.build()
        self.budget = daily.DailyBudget(self.store, self.adapters.billing()[0], self.config.inventory)
        self.broker = self.broker_for()
        self.call()
        self.budget.tariff, self.budget.inventory = self.adapters.billing()
        report = self.budget.summary()
        self.assertGreater(report["admission_total_at_observed_rates_nanos"], 500000000)
        self.assertFalse(report["verified_all_in_ceiling"])

    def test_lower_epoch_does_not_erase_prior_or_day_fee(self):
        tariff, inventory = self.adapters.billing()
        first = replace(tariff, prior_upper_usd="3", fixed_day_fee_usd="2")
        budget = daily.DailyBudget(self.store, first, inventory)
        budget.reserve_inference("unsent", "0.1", provenance="SYNTHETIC reservation commits original day facts")
        lower = replace(first, basis_sha256="c"*64, prior_upper_usd="0", fixed_day_fee_usd="0")
        report = daily.DailyBudget(self.store, lower, inventory).summary()
        self.assertGreaterEqual(report["admission_total_at_observed_rates_nanos"], 5100000000)

    def test_missing_pending_after_first_post_cannot_admit_a_new_request(self):
        self.call()
        self.changes = {"pending": []}
        before = self.budget._load()
        with self.assertRaisesRegex(daily.DailyAdmissionError, "pending exposure"):
            self.call(key="new-original")
        self.assertEqual(self.budget._load(), before)
        self.assertEqual(sum(method == "POST" and path == "/v1/responses" for method,path,*_ in self.transport.calls), 1)

    def test_unknown_basis_is_readable_and_hash_bound_without_admission(self):
        doc = self.basis(); doc["fees_taxes"]["tax_fraction_upper"] = None
        doc["pending"] = [{"key": "original", "upper_usd": None, "provenance": None}]
        basis = self.parsed(doc)
        self.assertFalse(basis.status()["fees_taxes_known"])
        self.assertEqual(basis.status()["pending_unknown_keys"], ["original"])
        saved = basis.document; saved["future_rate_lock"] = True
        self.assertFalse(basis.document["future_rate_lock"])
        with self.assertRaises(CostBasisError): basis.require_admission_facts()

    def test_initial_profile_basis_can_expire_for_original_get_recovery_only(self):
        self.models["cost_basis"]["observed_at"] -= 86400
        self.models["cost_basis"]["refresh_by"] -= 86400
        self.model_file = self.f.file("models-old-origin.json", json.dumps(self.models).encode())
        self.inputs = replace(self.inputs, models=self.model_file)
        bridge = _Bridge(self.config, self.inputs, time.time, cleanup_only=True)
        # This grants no paid authority; a separate fresh billing epoch remains mandatory.
        self.assertTrue(bridge.cleanup_only)
        self.assertEqual(self.transport.calls, [])

    def test_original_cache_corruption_refuses_before_any_provider_operation(self):
        original = self.budget._load()
        self.store.put(daily.STATE_KEY, {**original, "baseline": {**original["baseline"], "upper_usd": "0.01"}})
        with self.assertRaisesRegex(daily.DailyAdmissionError, "immutable history"): self.build()
        self.assertEqual(self.transport.calls, [])

    def test_legacy_paused_resumed_resource_keeps_high_observed_price_on_refresh(self):
        from league.tests.test_native_paused_budget import NativePausedBudget
        fixture = NativePausedBudget("runTest"); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.attached_then_elapsed(); fixture.pause()
        fixture.budget.reserve_resume("gym", "resume", provenance="SYNTHETIC original resume")
        fixture.budget.dispatch_resume("gym", "resume")
        at = fixture.clock()
        observed = daily.ObservedTariffEvidence(fixture.tariff.scope, "0.02", "0.009", "0.0008", "0.000411",
            at-1, at+120, "SYNTHETIC observed high price", "observed_self_service", "a"*64, False,
            "0", "2026-10-04", "0", (("gym", "1"),))
        budget = daily.DailyBudget(fixture.store, observed, fixture.inventory)
        budget.reserve_inference("unsent", "0.1", provenance="SYNTHETIC commit high epoch")
        high = budget.summary()["resource_upper_nanos"]
        lower = replace(observed, basis_sha256="b"*64, vcpu_usd_hour="0.001",
                        memory_gib_usd_hour="0.001", disk_gib_usd_hour="0.0001")
        self.assertGreater(high, 15*daily.NANOS)
        self.assertEqual(daily.DailyBudget(fixture.store, lower, fixture.inventory).summary()["resource_upper_nanos"], high)

    def test_terminal_resource_readback_retains_added_exposure_across_utc(self):
        self.broker.authorize_peer(os.getpid(), os.getuid(), os.getgid())
        self.broker._ensure_gym()
        key, row = next(iter(self.budget._load()["resources"].items()))
        tariff, inventory = self.adapters.billing()
        high = replace(tariff, pending=((key, "6"),))
        budget = daily.DailyBudget(self.store, high, inventory)
        budget.reserve_inference("unsent", "0.1", provenance="SYNTHETIC commit pending resource exposure")
        budget.terminal_observed(key, row["resource_id"], observed_at=time.time(), status="terminated",
                                 provenance="SYNTHETIC exact terminal GET, not invoice")
        tomorrow = (int(time.time()//86400)+1)*86400+1
        future = replace(high, valid_from=tomorrow-1, valid_until=tomorrow+120,
                         prior_utc_day=dt.datetime.fromtimestamp(tomorrow,dt.timezone.utc).date().isoformat())
        inv = replace(inventory, observed_at=tomorrow-1, valid_until=tomorrow+120)
        self.store.clock = lambda: tomorrow
        report = daily.DailyBudget(self.store, future, inv).summary()
        self.assertGreaterEqual(report["resource_upper_nanos"], 6*daily.NANOS)
        with self.assertRaisesRegex(daily.DailyAdmissionError, "pending exposure"):
            daily.DailyBudget(self.store, replace(future, pending=()), inv).summary()

    def test_balanced_original_get_recovery_keeps_hold_after_price_expiry(self):
        queued = {"id": "resp_original-balanced", "model": STOCK["k3_balanced"][0], "status": "queued"}
        self.transport.model_reply = queued
        ticks = iter((0, 31))
        self.adapters = build_sail_host_adapters(self.config, inputs=self.inputs, key_source=lambda: "UNUSED",
            box_transport=self.transport, inference_transport=self.transport, poll_monotonic=lambda: next(ticks))
        self.broker = self.broker_for()
        with self.assertRaisesRegex(ResearchCapabilityError, "pending"): self.call(profile="k3_balanced")
        hold = self.budget._load()["inference"]
        gets = []
        def transport(method, path, body=None, **options):
            self.assertEqual((method, path), ("GET", "/v1/responses/resp_original-balanced"))
            gets.append(path)
            return {**queued, "status": "completed", "output": []}
        expired = time.time()+2*86400
        adapters = build_sail_host_adapters(self.config, inputs=self.inputs, key_source=lambda: "UNUSED",
            box_transport=self.transport, inference_transport=transport, clock=lambda: expired,
            cleanup_only=True, poll_monotonic=lambda: 0)
        self.adapters = adapters
        # Passive retrieval authenticates the original peer without calling fresh
        # admission. Model source/bodies/handle/holds remain unchanged.
        self.broker = self.broker_for()
        self.broker._verify = lambda peer, **kw: IsolationProof(self.f.policy.scope, peer, os.getuid(),
            str(self.f.broker_root), kw["policy_digest"], "namespaces", time.time(), time.time()+60,
            self.f.runbook.sha256, "b"*64, "c"*64, self.f.adapter_file.sha256,
            tuple(sorted(ISOLATION_FACTS|NAMESPACE_FACTS)), "SYNTHETIC passive-only peer")
        result = self.call(profile="k3_balanced")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(gets, ["/v1/responses/resp_original-balanced"])
        self.assertEqual(self.budget._load()["inference"], hold)
        self.assertEqual(sum(method == "POST" and path == "/v1/responses" for method,path,*_ in self.transport.calls), 1)

    def test_complete_fabricated_all_in_original_bill_settles_actual_model_path(self):
        raw = self.f.file("SYNTHETIC-raw-original-invoice.bin", b"SYNTHETIC all-in final bill source without local JSON fields")
        def bill(key, response):
            bridge = self.adapters.provider.bridge
            intent = bridge.journal("intent", "model:"+key)
            value = {"schema": 2, "scope": self.f.policy.scope, "request_key": key, "response_id": response,
                     "model": STOCK["flash41_asap"][0], "body_sha256": intent["body_sha256"],
                     "actual_usd": "0.1", "accrued_day": dt.datetime.now(dt.timezone.utc).date().isoformat(),
                     "final": True, "inclusive_fees_taxes": True,
                     "source_document": {"path": str(raw.path), "sha256": raw.sha256}, "provenance": "SYNTHETIC reviewed full original invoice"}
            return self.f.file("all-in-original-bill.json", json.dumps(value).encode())
        self.inputs = replace(self.inputs, bill=bill)
        self.adapters = self.build(); self.broker = self.broker_for()
        result = self.call()
        self.assertEqual(result["cost_usd"], "0.1")
        self.assertEqual(result["cost_status"], "vendor_actual")
        self.assertIsNotNone(next(iter(self.budget._load()["inference"].values()))["receipt"])

    def test_observed_pause_savings_refuse_without_changing_original_full_hold(self):
        from league.tests.test_native_paused_budget import NativePausedBudget
        fixture = NativePausedBudget("runTest"); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.attached_then_elapsed()
        at = fixture.clock()
        tariff = daily.ObservedTariffEvidence(fixture.tariff.scope, "0.0150012", "0.008", "0.0007", "0.000411",
            at-1, at+120, "SYNTHETIC observed prices", "observed_self_service", "a"*64, False,
            "0", "2026-10-04", "0", (("gym", "14"),))
        budget = daily.DailyBudget(fixture.store,tariff,fixture.inventory)
        before = budget._load()
        with self.assertRaisesRegex(daily.DailyAdmissionError,"full hold retained"):
            budget.paused_observed("gym",observation=fixture.observation(),fence=fixture.fence(),
                                  retained_native_usage_upper_usd="0.28",usage_provenance="SYNTHETIC incomplete interval")
        self.assertEqual(budget._load(),before)

"""Credential-free adapter contracts using only synthetic brokers and temporary SQLite."""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from decimal import Decimal
from unittest import mock

from league.swarm import settings as S
from league.swarm.models import ModelError
from league.swarm.pool import GymJob, PoolError
from league.swarm.research_adapters import (ResearchGymPool, ResearchModelRouter, ResearchModelResponse,
                                           record_research_cost, reviewed_tools, _STATE, _load)
from league.swarm.researcher import Researcher
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock, result


class Broker:
    """Host-shaped fake: costs/dispatch slots/resources stay outside the adapters."""
    def __init__(self):
        self.model_calls, self.gym_calls = [], []
        self.cache = {}
        self.lost_model = self.lost_gym = False
        self.unknown_cost = False
        self.terminal_status = "completed"
        self.responses = []
        self.entered, self.release = threading.Event(), None
        self.image, self.bundle = "sbcp_synthetic_train", "gym-engine-synthetic"
        self.execution = "a" * 64  # Explicit synthetic reviewed artifact identity, not a runtime bypass.

    def cached_result(self, key, *, kind):
        return copy.deepcopy(self.cache.get((kind, key)))

    def evaluate(self, profile, items, *, key, **kwargs):
        self.model_calls.append((profile, copy.deepcopy(items), key, kwargs))
        if self.lost_model:
            raise TimeoutError("synthetic credential-looking provider body MUST NOT ESCAPE")
        output = self.responses.pop(0) if self.responses else [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"families": []}'}]}]
        answer = {"status": self.terminal_status, "output": output, "usage": {}, "profile": profile, "request_key": key,
                  "cost_usd": None if self.unknown_cost else "0.001",
                  "accrued_day": None if self.unknown_cost else "2026-10-04"}
        if self.unknown_cost:
            answer.update(cost_upper_usd="0.02", cost_status="unknown")
        self.cache["model", key] = answer
        return copy.deepcopy(answer)

    def run_gym(self, job, *, key):
        self.gym_calls.append((copy.deepcopy(job), key))
        self.entered.set()
        if self.release is not None:
            if not self.release.wait(5):
                raise TimeoutError("synthetic test did not release host")
        if self.lost_gym:
            raise TimeoutError("synthetic lost worker answer")
        row = result("synthetic", window=job["window"], roots=tuple(job["roots"]), t=4.0)
        row.update(run_id="synthetic-" + key, stress=job["stress"])
        answer = {"batch": {"trials": 1, "window": job["window"]}, "results": [row],
                  "gym_image": self.image, "gym_bundle": self.bundle, "gym_execution": self.execution,
                  "execution": {"capital": "10000", "workers": 8,
                                **{field: job[field] for field in ("split", "window", "start", "end", "roots", "stress")}}}
        self.cache["gym", key] = answer
        return copy.deepcopy(answer)


class ResearchAdapters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock(dt.datetime(2026, 10, 4, 10, tzinfo=dt.timezone.utc).timestamp())
        self.store = SwarmStore(Path(self.tmp.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.broker = Broker()
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["researcher"].update(claude_top=0, top_families=0, rewrites_per_day=0)
        self.settings["tournament"].update(require_robustness=False, drift_screen=False)
        self.router = ResearchModelRouter(self.store, self.broker, settings=self.settings)
        self.pool = ResearchGymPool(self.store, self.broker, checkpoint=self.broker.image, bundle=self.broker.bundle,
                                    execution=self.broker.execution, train_first="2022-01-03", roots=("SPY",), settings=self.settings)
        self.addCleanup(self.pool.stop)
        self.spec = next(spec for spec in SEEDS if spec["id"] == "condor-vrp")
        self.family = self.store.add_family(family_spec(self.spec), origin="seed")
        self.code, self.params = program_for(self.spec)

    def job(self, **kwargs):
        return GymJob(**{"family": self.family["id"], "version": 1, "code": self.code, "params": self.params,
                         "window": "train", "roots": ("SPY",), **kwargs})

    def model(self, key="model", items=None):
        return self.router.sail("flash_asap", items or [{"role": "user", "content": "synthetic research request"}],
                                family=self.family["id"], key=key)

    def test_stock_researcher_starter_and_tournament_use_scoped_adapters_and_preserve_trials(self):
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock,
                                starter=program_for, background=False)
        starter = researcher.cycle(self.family["id"])
        self.assertTrue(starter.get("starter"), starter)
        self.assertEqual(self.broker.model_calls, [])
        # A starter also submits its stock mid/stress/drift robustness jobs. Their
        # actual trials remain counted when they land through their original callbacks.
        for job, _, _ in list(self.pool._jobs.values()):
            self.pool.wait(job, 2)
        before = self.store.family(self.family["id"])["trials"]
        self.assertGreaterEqual(before, 1)
        tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        row = tournament.run()
        self.assertIn(self.family["id"], row["validation"]["judged"])
        self.assertEqual(self.store.family(self.family["id"])["trials"], before + 2)
        self.assertEqual(self.broker.gym_calls[-1][0]["window"], "validation")
        calls = len(self.broker.gym_calls)
        tournament.run()
        self.assertEqual(len(self.broker.gym_calls), calls)
        self.assertEqual(self.store.family(self.family["id"])["trials"], before + 2)

    def test_stock_researcher_tool_turns_use_broker_model_and_train_jobs(self):
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock,
                                starter=program_for, background=False)
        researcher.cycle(self.family["id"])
        for job, _, _ in list(self.pool._jobs.values()):
            self.pool.wait(job, 2)
        before = self.store.family(self.family["id"])["trials"]
        self.broker.responses = [[{"type": "function_call", "name": "gym_run", "call_id": "call1",
                                  "arguments": json.dumps({"code": self.code, "params": {**self.params, "vrp_min": 1.5}})}],
                                 [{"type": "message", "content": [{"type": "output_text", "text": "Synthetic turn complete."}]}]]
        row = researcher.cycle(self.family["id"])
        self.assertNotIn("error", row, row)
        self.assertEqual(row["model_calls"], 2)
        self.assertEqual(row["tool_calls"], 1)
        for job, _, _ in list(self.pool._jobs.values()):
            self.pool.wait(job, 2)
        self.assertGreater(self.store.family(self.family["id"])["trials"], before)
        self.assertEqual(self.store.spent(["sail_model"]), 0.002)
        self.assertEqual(self.broker.model_calls[0][3]["tool_choice"], "required")
        self.assertTrue(self.broker.model_calls[0][3]["tools"])

    def test_model_terminal_cache_survives_router_restart_and_books_once(self):
        response = self.model()
        self.assertEqual(str(response.cost_usd), "0.001")
        self.router = ResearchModelRouter(self.store, self.broker, settings=self.settings)
        self.model()
        self.assertEqual(len(self.broker.model_calls), 1)
        self.assertEqual(self.store.spent(["sail_model"]), 0.001)
        with self.assertRaises(ModelError): self.model(items=[{"role": "user", "content": "changed"}])
        self.assertEqual(len(self.broker.model_calls), 1)

    def test_duplicate_nonfinite_and_bool_changed_journal_values_fail_closed(self):
        self.model()
        good = self.store._one("SELECT value FROM kv WHERE key=?", (_STATE,))["value"]
        row = json.loads(good)["model:model"]
        duplicate = '{"model:model":' + json.dumps(row) + ',"model:model":' + json.dumps(row) + '}'
        bad_nan, bad_bool = json.loads(good), json.loads(good)
        bad_nan["model:model"]["accounted"] = math.nan
        bad_bool["model:model"]["accounted"] = 0
        variants = [duplicate, json.dumps(bad_nan), json.dumps(bad_bool)]
        for index, raw in enumerate(variants):
            self.store._exec("UPDATE kv SET value=? WHERE key=?", (raw, _STATE))
            with self.subTest(index=index), self.assertRaises(ModelError): self.model(key=f"new-{index}")
        self.assertEqual(len(self.broker.model_calls), 1)

    def test_provider_succeeded_terminal_status_maps_to_completed_response(self):
        answer = self.broker.evaluate("flash_asap", [], key="succeeded")
        answer["status"] = "succeeded"
        self.broker.evaluate = mock.Mock(return_value=answer)
        response = self.model(key="succeeded")
        self.assertEqual(response.status, "completed")
        self.assertEqual(self.store.spent(["sail_model"]), 0.001)

    def test_lost_model_reply_never_redispatches_and_error_does_not_expose_host_text(self):
        self.broker.lost_model = True
        for _ in range(2):
            with self.assertRaises(ModelError) as found: self.model()
            self.assertNotIn("credential-looking", str(found.exception))
        self.assertEqual(len(self.broker.model_calls), 1)
        self.assertEqual(self.store.spent(["sail_model"]), 0)

    def test_host_terminal_cache_can_recover_lost_controller_response_without_dispatch(self):
        self.broker.lost_model = True
        with self.assertRaises(ModelError): self.model()
        self.broker.cache["model", "model"] = {"status": "completed", "output": [], "usage": {},
                                               "profile": "flash_asap", "request_key": "model", "cost_usd": "0.001",
                                               "accrued_day": "2026-10-04"}
        self.model()
        self.assertEqual(len(self.broker.model_calls), 1)
        self.assertEqual(self.store.spent(["sail_model"]), 0.001)

    def test_unknown_terminal_invoice_returns_output_and_bound_without_actual_spend_or_replay(self):
        self.broker.unknown_cost = True
        for _ in range(2):
            response = self.model()
            self.assertIsNone(response.cost_usd)
            self.assertEqual(response.cost_upper_usd, Decimal("0.02"))
            self.assertEqual(response.cost_status, "unknown")
            self.assertEqual(response.output_text, '{"families": []}')
        self.assertEqual(len(self.broker.model_calls), 1)
        self.assertEqual(self.store.spent(["sail_model"]), 0)
        self.assertEqual(self.store.family(self.family["id"])["spent_usd"], 0)
        receipt = _load(self.store)["model:model"]["result"]
        self.assertIsNone(receipt["cost_usd"])
        self.assertIsNone(receipt["accrued_day"])

    def test_unknown_invoice_requires_finite_positive_original_reservation_and_no_fake_day(self):
        self.broker.unknown_cost = True
        original = self.broker.evaluate
        variants = [{"cost_upper_usd": value} for value in (None, "0", "-1", "NaN", "Infinity", "25.000000001", 1)]
        variants += [{"accrued_day": "2026-10-04"}, {"cost_status": "vendor_actual"}]
        for index, variant in enumerate(variants):
            def changed(*args, **kwargs):
                return {**original(*args, **kwargs), **variant}
            self.broker.evaluate = changed
            with self.subTest(variant=variant), self.assertRaises(ModelError):
                self.model(key=f"invalid-upper-{index}")
        self.assertEqual(self.store.spent(["sail_model"]), 0)

    def test_unknown_invoice_ask_and_stock_hold_report_actual_null_and_preserve_trials(self):
        self.broker.unknown_cost = True
        answer = self.router.ask(role="architect", system="s", user="u", family=None, key="unknown-ask",
                                 sail_profile="flash_asap")
        self.assertIsNone(answer["cost_usd"])
        self.assertEqual((answer["cost_upper_usd"], answer["cost_status"]), ("0.02", "unknown"))
        self.assertEqual(answer["json"], {"families": []})
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock,
                                starter=program_for, background=False)
        researcher.cycle(self.family["id"])
        for job, _, _ in list(self.pool._jobs.values()):
            self.pool.wait(job, 2)
        before = self.store.family(self.family["id"])["trials"]
        gym_before = len(self.broker.gym_calls)
        self.broker.responses = [[{"type": "function_call", "name": "gym_run", "call_id": "hold1",
                                  "arguments": json.dumps({"hold": True, "note": "No fresh evidence in this synthetic fixture."})}]]
        row = researcher.cycle(self.family["id"])
        self.assertNotIn("error", row, row)
        self.assertTrue(row["hold"], row)
        self.assertIsNone(row["cost_usd"])
        self.assertEqual((row["cost_upper_usd"], row["cost_status"]), ("0.02", "unknown"))
        self.assertEqual(Decimal(row["cost_actual_known_usd"]), Decimal(0))
        self.assertEqual(self.store.family(self.family["id"])["trials"], before)
        self.assertEqual(len(self.broker.gym_calls), gym_before)
        self.assertEqual(self.store.spent(["sail_model"]), 0)

    def test_mixed_known_unknown_turns_keep_actual_total_unknown_and_reservations_separate(self):
        from ltcm.provider import ProviderResponse
        out = {"cost_usd": 0.0}
        for actual in (Decimal("0.001"), None, Decimal("0.002")):
            stock = ProviderResponse("k", "r", "completed", "", [], [], [], {}, actual, False)
            record_research_cost(out, ResearchModelResponse(stock, Decimal("0.02"), "unknown" if actual is None else "vendor_actual"))
        self.assertIsNone(out["cost_usd"])
        self.assertEqual(Decimal(out["cost_actual_known_usd"]), Decimal("0.003"))
        self.assertEqual(Decimal(out["cost_upper_usd"]), Decimal("0.06"))
        self.assertEqual(out["cost_status"], "unknown")

    def test_stock_failed_terminal_actors_report_unknown_actual_and_retained_bound(self):
        from league.swarm.architect import Architect
        self.broker.unknown_cost = True
        self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock,
                                background=False)
        architect = Architect(self.store, self.router, self.settings, clock=self.clock)
        for status in ("failed", "cancelled"):
            self.broker.terminal_status = status
            self.clock.advance(1)
            cycle = researcher.cycle(self.family["id"])
            pass_result = architect.run()
            for row in (cycle, pass_result):
                self.assertIn("error", row, row)
                self.assertIsNone(row["cost_usd"])
                self.assertEqual((row["cost_upper_usd"], row["cost_status"]), ("0.02", "unknown"))
                self.assertEqual(row["billed"][0]["status"], status)
            self.assertEqual(cycle["model_calls"], 1)
        self.assertEqual(self.store.spent(["sail_model"]), 0)
        self.assertEqual(self.store.family(self.family["id"])["spent_usd"], 0)

    def test_stock_architect_usable_unknown_terminal_keeps_cost_evidence(self):
        from league.swarm.architect import Architect
        self.broker.unknown_cost = True
        out = Architect(self.store, self.router, self.settings, clock=self.clock).run()
        self.assertNotIn("error", out, out)
        self.assertIsNone(out["cost_usd"])
        self.assertEqual((out["cost_upper_usd"], out["cost_status"]), ("0.02", "unknown"))
        self.assertEqual(out["born"], [])

    def test_stock_actor_legacy_known_failure_reports_actual_without_inventing_original_reservation(self):
        self.broker.terminal_status = "failed"
        self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        row = researcher.cycle(self.family["id"])
        self.assertEqual(row["cost_usd"], 0.001)
        self.assertEqual(row["cost_status"], "vendor_actual")
        self.assertIsNone(row["billed"][0]["cost_upper_usd"])
        self.assertEqual(self.store.spent(["sail_model"]), 0.001)

    def test_malformed_unknown_terminal_fields_still_report_reservation_in_actor_error(self):
        self.broker.unknown_cost = True
        self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        original = self.broker.evaluate
        self.broker.evaluate = lambda *args, **kwargs: {**original(*args, **kwargs), "incomplete_details": "bad"}
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        row = researcher.cycle(self.family["id"])
        self.assertIn("error", row)
        self.assertIsNone(row["cost_usd"])
        self.assertEqual((row["cost_upper_usd"], row["cost_status"]), ("0.02", "unknown"))
        self.assertEqual(self.store.spent(["sail_model"]), 0)

    def test_async_rewrite_cost_is_recorded_separately_from_calling_cycle(self):
        self.broker.unknown_cost = True
        self.settings["researcher"]["rewrites_per_day"] = 1
        self.broker.responses = [[{"type": "message", "content": [{"type": "output_text", "text": "```python\n" + self.code + "```"}]}]]
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        cycle = {"model_calls": 0, "tool_calls": 0, "cost_usd": 0.0}
        self.assertTrue(researcher.request_rewrite(self.family, cycle))
        self.assertEqual(cycle["cost_usd"], 0.0, "asynchronous rewrite is a separate cost receipt")
        costs = [e["payload"] for e in self.store.events_after(0)
                 if e["kind"] == "swarm.research" and e["payload"].get("action") == "rewrite_cost"]
        self.assertEqual(len(costs), 1)
        self.assertIsNone(costs[0]["cost_usd"])
        self.assertEqual((costs[0]["cost_upper_usd"], costs[0]["cost_status"]), ("0.02", "unknown"))
        self.assertFalse(costs[0]["counted"], "a cost receipt is no literature request")
        from league.swarm.library import Library
        self.assertEqual(Library(self.store, None, self.settings, clock=self.clock).used(), (0, {}))
        self.assertIn("rewrite_ready", self.store.family(self.family["id"])["state"])

    def test_gateway_routes_and_role_without_profile_are_denied(self):
        self.assertFalse(self.router.claude_enabled("researcher"))
        with self.assertRaises(ModelError): self.router.claude_turn()
        with self.assertRaises(ModelError):
            self.router.ask(role="architect", system="s", user="u", family=None, key="a", sail_profile=None,
                            openai_model="unrestricted", claude=True)
        self.assertEqual(self.broker.model_calls, [])
        row = self.router.ask(role="architect", system="s", user="u", family=None, key="a",
                              sail_profile="flash_asap", openai_model="ignored", claude=True)
        self.assertEqual(row["json"], {"families": []})
        self.assertEqual(row["route"], "sail")
        self.assertEqual(len(self.broker.model_calls), 1)

    def test_construction_uses_no_provider_client_gateway_or_environment_factory(self):
        with mock.patch("ltcm.provider.Provider", side_effect=AssertionError("provider forbidden")), \
                mock.patch("league.sailbox.SailboxClient", side_effect=AssertionError("client forbidden")), \
                mock.patch("league.swarm.models.build_router", side_effect=AssertionError("factory forbidden")):
            self.router = ResearchModelRouter(self.store, self.broker, settings=self.settings)
            self.model()
            self.pool.run(self.job(), timeout=2)

    def test_missing_or_partial_controller_receipts_cannot_create_a_fresh_dispatch(self):
        self.model()
        self.store.put(_STATE, {})
        with self.assertRaises(ModelError): self.model(key="new-model")
        self.assertEqual(len(self.broker.model_calls), 1)
        self.store._exec("DELETE FROM kv WHERE key=?", (_STATE,))
        with self.assertRaises(ModelError): self.model(key="another-model")
        self.assertEqual(len(self.broker.model_calls), 1)

    def test_sealed_live_date_and_root_escapes_are_denied_before_broker(self):
        changes = [{"window": "holdout"}, {"window": "forward"}, {"gate": "sealed"},
                   {"purpose": "prefilter"}, {"purpose": "holdout"}, {"roots": ("QQQ",)},
                   {"start": "2021-12-31"}, {"end": "2025-01-02"}, {"stress": math.nan}, {"split": True}]
        for fields in changes:
            job = self.job()
            for field, value in fields.items(): setattr(job, field, value)
            with self.subTest(fields=fields), self.assertRaises(PoolError): self.pool.submit(job)
        with self.assertRaises(PoolError): self.pool.image("gate")
        self.assertEqual(self.broker.gym_calls, [])

    def test_validation_serialization_is_accepted_by_actual_host_job_contract(self):
        from league.swarm.daily_compute import ResourceBound
        from league.swarm.research_transport import ResearchBroker, ResearchPolicy
        bound = ResourceBound("synthetic-gym", "gym", 1, "1", "1", "0", "0", "synthetic ceilings")
        host = ResearchBroker.__new__(ResearchBroker)
        host.policy = ResearchPolicy("synthetic", "sbcp_" + "a" * 32, "gym-engine-synthetic", bound, ("SPY",), "a" * 64,
                                     train_first="2022-01-03")
        job = self.job()
        job.window, job.purpose = "validation", "validation"
        payload = self.pool._payload(job)
        reviewed = host._job(payload)
        self.assertIsNone(reviewed.start)
        self.assertIsNone(reviewed.end)
        for field in ("start", "end"):
            custom = self.job()
            custom.window, custom.purpose = "validation", "validation"
            setattr(custom, field, "2025-01-02")
            with self.assertRaises(PoolError): self.pool.submit(custom)

    def test_actual_broker_handle_contract_accepts_adapters_without_unrestricted_clients(self):
        from league.tests.test_research_transport import ResearchTransport
        fixture = ResearchTransport(methodName="test_open_runtime_has_no_paid_activity_or_resources")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        class Client:
            def evaluate(self, profile, items, *, key, **options):
                return fixture.call("evaluate", {"profile": profile, "items": items, "key": key, **options})
            def run_gym(self, job, *, key):
                return fixture.call("run_gym", {"job": job, "key": key})
            def cached_result(self, key, *, kind):
                return fixture.call("cached_result", {"key": key, "kind": kind})
        client = Client()
        settings = copy.deepcopy(self.settings)
        settings["gym"]["workers"] = fixture.policy.workers
        router = ResearchModelRouter(self.store, client, settings=settings)
        response = router.sail("reviewed", [{"role": "user", "content": "synthetic"}], key="actual-contract-model",
                               family=self.family["id"], max_output=1000)
        self.assertEqual(str(response.cost_usd), "0.0005")
        pool = ResearchGymPool(self.store, client, checkpoint=fixture.policy.checkpoint, bundle=fixture.policy.gym_bundle,
                               execution=fixture.policy.execution, train_first="2022-01-03", roots=("SPY",), settings=settings)
        self.addCleanup(pool.stop)
        train = pool.run(self.job(), timeout=2)
        self.assertEqual(train["research_execution"]["workers"], fixture.policy.workers)
        validation = self.job()
        validation.window, validation.purpose = "validation", "validation"
        self.assertEqual(pool.run(validation, timeout=2)["window"], "validation")
        self.assertEqual(len(fixture.provider.creates), 1)
        self.assertEqual(len(fixture.driver_calls), 2)
        self.assertEqual(len(fixture.model_calls), 1)

    def test_stock_function_tools_reach_actual_broker_in_exact_reviewed_provider_shape(self):
        from dataclasses import replace
        from ltcm.provider import Provider
        from league.tests.test_research_transport import ResearchTransport
        fixture = ResearchTransport(methodName="test_open_runtime_has_no_paid_activity_or_resources")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        stock = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        tools = stock.tools(revise=True, retire=False)
        expected = [Provider._tool_entry(tool) for tool in tools]
        self.assertEqual(reviewed_tools(tools), expected)
        fixture.model_policy = replace(fixture.model_policy, allowed_tools=tuple(expected))
        fixture.broker = fixture.make_broker()
        class Client:
            def evaluate(self, profile, items, *, key, **options):
                return fixture.call("evaluate", {"profile": profile, "items": items, "key": key, **options})
        router = ResearchModelRouter(self.store, Client(), settings=self.settings)
        router.sail("reviewed", [{"role": "user", "content": "synthetic stock tool turn"}], tools=tools,
                    key="actual-stock-tools", family=self.family["id"], max_output=1000)
        self.assertEqual(fixture.model_calls[0]["tools"], expected)
        self.assertEqual(_load(self.store)["model:actual-stock-tools"]["request"]["tools"], expected)
        self.assertEqual(tools, stock.tools(revise=True, retire=False), "normalization must not mutate stock schemas")

    def test_builtin_or_unreviewed_tool_fields_are_rejected_before_claim_or_ipc(self):
        valid = {"name": "gym_run", "description": "Synthetic local tool", "parameters": {"type": "object"}}
        for changes in ({"type": "web_search"}, {"url": "https://example.invalid"}, {"strict": 1}):
            with self.subTest(changes=changes), self.assertRaises(ModelError):
                self.router.sail("flash_asap", [{"role": "user", "content": "synthetic"}],
                                 tools=[{**valid, **changes}], family=self.family["id"], key="denied-tool")
        self.assertEqual(_load(self.store), {})
        self.assertEqual(self.broker.model_calls, [])

    def test_mismatched_actual_execution_cannot_be_adopted_or_charged_as_qualified_trial(self):
        original = self.broker.run_gym
        def wrong_execution(job, *, key):
            answer = original(job, key=key)
            answer["execution"]["capital"] = "20000"
            return answer
        self.broker.run_gym = wrong_execution
        with self.assertRaises(PoolError): self.pool.run(self.job(), timeout=2)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)
        self.assertIsNone(next(iter(_load(self.store).values()))["result"])
        self.assertEqual(next(iter(_load(self.store).values()))["rejected"]["execution"]["capital"], "20000")

    def test_execution_fingerprint_is_required_and_mismatch_is_archived_without_redispatch(self):
        with self.assertRaises(ValueError):
            ResearchGymPool(self.store, self.broker, checkpoint=self.broker.image, bundle=self.broker.bundle,
                            execution="", train_first="2022-01-03", roots=("SPY",), settings=self.settings)
        self.broker.execution = "b" * 64
        with self.assertRaises(PoolError): self.pool.run(self.job(), timeout=2)
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["unresolved"], 1)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)
        self.assertEqual(next(iter(_load(self.store).values()))["rejected"]["gym_execution"], "b" * 64)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def actors(self):
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock,
                                starter=program_for, background=False)
        return researcher, Tournament(self.store, self.pool, self.settings, clock=self.clock)

    def restart_pool(self, *, image=None):
        self.assertTrue(self.pool.stop())
        self.pool = ResearchGymPool(self.store, self.broker, checkpoint=image or self.broker.image,
                                    bundle=self.broker.bundle, execution=self.broker.execution,
                                    train_first="2022-01-03", roots=("SPY",), settings=self.settings)
        self.addCleanup(self.pool.stop)

    def test_restart_recovers_original_terminal_receipt_once_without_redispatch(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        self.broker.lost_gym = True
        with self.assertRaises(PoolError): self.pool.run(self.job(version=version["n"]), timeout=2)
        sent, key = self.broker.gym_calls[0]
        # The host completed after the controller lost its reply; only cache readback is allowed.
        self.broker.lost_gym = False
        answer = self.broker.run_gym(sent, key=key)
        calls = len(self.broker.gym_calls)
        self.restart_pool()
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament), {"recovered": 1, "unresolved": 0})
        recovered = self.store.runs(self.family["id"])[0]
        self.assertEqual(recovered["version"], version["n"])
        self.assertEqual(self.store.family(self.family["id"])["trials"], 1)
        self.pool.recover(researcher=researcher, tournament=tournament)
        again = self.pool.run(self.job(version=version["n"]), timeout=2)
        self.store.add_run(self.family["id"], version["n"], again, window="train", stress=1, purpose="train")
        self.assertEqual(again["trials"], 0)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 1)
        self.assertEqual(len(self.broker.gym_calls), calls)

    def test_pending_same_evaluation_with_changed_version_cannot_make_alternate_paid_call(self):
        first = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        second = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        self.broker.lost_gym = True
        for version in (first["n"], second["n"]):
            with self.assertRaises(PoolError): self.pool.run(self.job(version=version), timeout=2)
        self.assertEqual(len(self.broker.gym_calls), 1)
        state = _load(self.store)
        self.assertEqual(len(state), 1)
        self.assertEqual(next(iter(state.values()))["request"]["job"]["version"], first["n"])

    def test_terminal_same_program_in_new_family_is_free_reuse_and_original_trial_counts_once(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        original = self.pool.run(self.job(version=version["n"]), timeout=2)
        self.store.add_run(self.family["id"], version["n"], original, window="train", stress=1, purpose="train")
        spec = {**family_spec(self.spec), "id": "synthetic-twin", "mechanism": "synthetic same-program twin"}
        child = self.store.add_family(spec, origin="architect")
        other = self.store.add_version(child["id"], self.code, self.params, author="synthetic")
        job = self.job(version=other["n"])
        job.family = child["id"]
        reused = self.pool.run(job, timeout=2)
        self.store.add_run(child["id"], other["n"], reused, window="train", stress=1, purpose="train")
        researcher, tournament = self.actors()
        self.pool.recover(researcher=researcher, tournament=tournament)
        self.assertEqual(reused["trials"], 0)
        self.assertEqual(self.store.family(child["id"])["trials"], 0)
        self.assertEqual(self.store.lineage_trials(child["id"]), 1)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_recovery_preserves_prior_cumulative_trial_total_and_adds_only_new_actual_trial(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        # A legacy cumulative row predates this broker request. A new actual receipt
        # must add one, while retries of that receipt must add nothing further.
        job = self.job(version=version["n"])
        payload = self.pool._payload(job)
        evaluation = {key: value for key, value in payload.items() if key not in ("family", "version", "purpose")}
        from league.swarm.researcher import params_of, merged_key
        from league.swarm.research_adapters import _digest
        evaluation["params"] = merged_key(params_of(job.code) or {}, job.params)
        key = "research-gym:" + _digest({"checkpoint": self.pool.checkpoint, "bundle": self.pool.version,
                                      "gym_execution": self.pool.execution, "evaluation": evaluation, "execution": self.pool._execution(payload)})
        old = result("legacy", window="train", roots=("SPY",))
        old.update(run_id="synthetic-" + key, stress=1, trials=7, gym_image=self.pool.checkpoint, gym_bundle=self.pool.version)
        self.store.add_run(self.family["id"], version["n"], old, window="train", stress=1, purpose="train")
        self.pool.run(job, timeout=2)
        self.restart_pool()
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["recovered"], 1)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 8)
        self.pool.recover(researcher=researcher, tournament=tournament)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 8)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_pending_explicit_default_params_are_the_same_evaluation_and_cannot_redispatch(self):
        from league.swarm.researcher import params_of
        self.broker.lost_gym = True
        implicit = self.job()
        implicit.params = {}
        explicit = self.job()
        explicit.params = params_of(self.code)
        for job in (implicit, explicit):
            with self.assertRaises(PoolError): self.pool.run(job, timeout=2)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_default_and_explicit_split_match_stock_pool_settings(self):
        default = self.pool._payload(self.job())
        self.assertEqual(default["split"], S.train_split(self.settings, dt.date(2022, 1, 3)))
        self.assertEqual(self.pool._payload(self.job(split=1))["split"], 1)
        self.settings["gym"]["train_split"] = 4
        self.restart_pool()
        self.assertEqual(self.pool._payload(self.job())["split"], 4)

    def test_uncertain_robustness_is_not_an_executed_failure_or_demotion(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        failures = []
        job = self.job(version=version["n"], purpose="robustness", stress=1.5)
        job.late_fail = failures.append
        self.broker.lost_gym = True
        with self.assertRaises(PoolError): self.pool.run(job, timeout=2)
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["unresolved"], 1)
        self.assertEqual(failures, [])
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_recovery_preserves_old_evaluator_archive_without_current_qualification(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        job = self.job(version=version["n"])
        job.window, job.purpose = "validation", "validation"
        self.store.update_family(self.family["id"], best_version=version["n"])
        self.pool.run(job, timeout=2)
        self.restart_pool(image="sbcp_new_synthetic_train")
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["recovered"], 1)
        family = self.store.family(self.family["id"])
        self.assertEqual(family["trials"], 2)
        self.assertIsNone(family["validated_version"])
        self.assertFalse(family["state"].get("gate_ready"))
        primary = next(row for row in self.store.runs(family["id"]) if row["stress"] == 1)
        self.assertEqual(primary["summary"].get("gym_image"), self.broker.image)

    def test_interrupted_validation_primary_recovers_twin_and_verdict_once(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        job = self.job(version=version["n"])
        job.window, job.purpose = "validation", "validation"
        self.store.update_family(self.family["id"], best_version=version["n"])
        answer = self.pool.run(job, timeout=2)
        self.store.add_run(self.family["id"], version["n"], answer, window="validation", stress=1, purpose="validation")
        self.restart_pool()
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["recovered"], 1)
        family = self.store.family(self.family["id"])
        self.assertEqual(family["trials"], 2)
        self.assertEqual(family["validations"], 1)
        self.assertEqual(family["validated_version"], version["n"])
        self.pool.recover(researcher=researcher, tournament=tournament)
        self.assertEqual(self.store.family(family["id"])["trials"], 2)
        self.assertEqual(self.store.family(family["id"])["validations"], 1)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_recovery_accounting_rollback_keeps_terminal_receipt_and_counts_once_after_retry(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        self.pool.run(self.job(version=version["n"]), timeout=2)
        self.restart_pool()
        researcher, tournament = self.actors()
        original = self.store.event
        def fail_marker(kind, family, payload):
            if kind == "swarm.research_adapter" and payload.get("action") == "accounted":
                raise RuntimeError("synthetic accounting commit interruption")
            return original(kind, family, payload)
        with mock.patch.object(self.store, "event", side_effect=fail_marker):
            self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament), {"recovered": 0, "unresolved": 1})
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)
        self.assertFalse(next(iter(_load(self.store).values()))["accounted"])
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament), {"recovered": 1, "unresolved": 0})
        self.assertEqual(self.store.family(self.family["id"])["trials"], 1)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_recovery_restores_robustness_figures_without_a_second_trial_or_dispatch(self):
        version = self.store.add_version(self.family["id"], self.code, self.params, author="synthetic")
        self.pool.run(self.job(version=version["n"], purpose="robustness", stress=1.5), timeout=2)
        self.restart_pool()
        researcher, tournament = self.actors()
        self.assertEqual(self.pool.recover(researcher=researcher, tournament=tournament)["recovered"], 1)
        family = self.store.family(self.family["id"])
        self.assertEqual(family["trials"], 1)
        self.assertEqual(family["state"]["robustness"][str(version["n"])]["stress_1.5"]["gym_image"], self.broker.image)
        self.pool.recover(researcher=researcher, tournament=tournament)
        self.assertEqual(self.store.family(family["id"])["trials"], 1)
        self.assertEqual(len(self.broker.gym_calls), 1)

    def test_gym_cache_retry_runs_no_second_evaluation_and_adapter_never_counts_trials(self):
        original = self.pool.run(self.job(), timeout=2)
        again = self.pool.run(self.job(), timeout=2)
        self.assertEqual(original["run_id"], again["run_id"])
        self.assertEqual(len(self.broker.gym_calls), 1)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)

    def test_cancel_queued_family_runs_nothing(self):
        self.broker.release = threading.Event()
        self.addCleanup(self.broker.release.set)
        active = self.job()
        active.family = "other-synthetic-family"
        self.pool.submit(active)
        self.assertTrue(self.broker.entered.wait(2))
        job = self.pool.submit(self.job())
        self.pool.cancel_family(job.family)
        with self.assertRaises(PoolError): self.pool.wait(job, 2)
        self.assertEqual(len(self.broker.gym_calls), 1)
        self.broker.release.set()
        self.pool.wait(active, 2)

    def test_lost_gym_reply_retains_request_and_same_scope_never_redispatches(self):
        self.broker.lost_gym = True
        for _ in range(2):
            with self.assertRaises(PoolError): self.pool.run(self.job(), timeout=2)
        self.assertEqual(len(self.broker.gym_calls), 1)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 0)

    def test_expired_caller_wait_delivers_actual_evaluation_to_original_late_callback(self):
        self.broker.release = threading.Event()
        self.addCleanup(self.broker.release.set)
        received, landed = [], threading.Event()
        job = self.pool.submit(self.job())
        def late(row):
            self.store.add_run(job.family, job.version, row, window="train", stress=1, purpose="train")
            received.append(row)
            landed.set()
        with self.assertRaises(PoolError): self.pool.wait(job, 0.001, late=late)
        self.assertTrue(self.broker.entered.wait(2))
        self.broker.release.set()
        self.assertTrue(landed.wait(2))
        self.assertEqual(len(received), 1)
        self.assertEqual(self.store.family(self.family["id"])["trials"], 1)
        self.pool.wait(job, 2)
        self.assertEqual(len(received), 1)

    def test_stock_operator_timeout_parks_original_evaluation_without_second_attempt(self):
        self.store.add_version(self.family["id"], self.code, self.params, author="operator-revive")
        self.broker.release = threading.Event()
        self.addCleanup(self.broker.release.set)
        researcher, _ = self.actors()
        original_wait = self.pool.wait
        def short_wait(job, timeout=None, **options):
            return original_wait(job, 0.001, **options)
        out = {"model_calls": 0, "tool_calls": 0, "cost_usd": 0.0}
        with mock.patch.object(self.pool, "wait", side_effect=short_wait):
            first = researcher._operator_run(self.store.family(self.family["id"]), out)
        self.assertTrue(first["retry"])
        self.assertTrue(self.broker.entered.wait(2))
        family = self.store.family(self.family["id"])
        record = researcher.operator_record(family, 1)
        self.assertEqual(record["tries"], 1)
        self.assertGreater(record["late_until"], self.clock())
        researcher._operator_run(family, {"model_calls": 0, "tool_calls": 0, "cost_usd": 0.0})
        self.assertEqual(researcher.operator_record(self.store.family(family["id"]), 1)["tries"], 1)
        self.assertEqual(len(self.broker.gym_calls), 1)
        self.broker.release.set()
        original_wait(next(iter(self.pool._jobs.values()))[0], 2)
        self.assertEqual(self.store.family(family["id"])["trials"], 1)


if __name__ == "__main__":
    unittest.main()

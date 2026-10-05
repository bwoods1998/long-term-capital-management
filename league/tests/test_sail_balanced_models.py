"""Offline stock Kimi balanced wire and original accepted-request recovery.

Every invoice, price bound, authority and native response is SYNTHETIC. There
are no keys, network calls or paid resources. A documented rate is not treated
as actual cost or proof of a production maximum-inclusive charge.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import datetime as dt
import hashlib
import json
import os
import threading
import unittest
from unittest import mock

from league.tests import test_sail_research_host as fixtures
from league.swarm.daily_compute import DailyAdmissionError
from league.swarm.models import ModelError
from league.swarm.research_adapters import ResearchModelRouter
from league.swarm.research_ipc import BrokerClient, BrokerServer, create_listener
from league.swarm.research_transport import ModelCapability, ModelPolicy, ResearchCapabilityError, EVENT_KIND
from league.swarm.sail_research_host import build_sail_host_adapters, HOST_EVENT
from league.swarm.store import SwarmStore


class Clock:
    def __init__(self):
        self.now = 0.0
        self.jump = None

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds if self.jump is None else self.jump


class Native:
    def __init__(self):
        self.calls = []
        self.post = self.reply("queued")
        self.gets = [self.reply("completed")]

    @staticmethod
    def reply(phase, **changes):
        return {"id": "resp_balanced-original", "model": "moonshotai/Kimi-K3", "status": phase,
                "output": [{"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": '{"code":"return []"}'}]}],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}, **changes}

    def __call__(self, method, path, body=None, **options):
        self.calls.append((method, path, body, options))
        if method == "POST" and path == "/v1/responses":
            response = self.post
        elif method == "GET" and path == "/v1/responses/resp_balanced-original":
            response = self.gets.pop(0) if len(self.gets) > 1 else self.gets[0]
        else:
            raise AssertionError("unexpected native route: " + method + " " + path)
        if isinstance(response, BaseException):
            raise response
        return json.loads(json.dumps(response))


class BalancedModels(unittest.TestCase):
    def setUp(self):
        self.native, self.clock = Native(), Clock()
        self.fx = fixtures.SailResearchHost("runTest")
        self.fx.build = self.build
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.controller = SwarmStore(self.fx.f.base / "balanced-controller")
        self.addCleanup(self.controller.close)
        self.router = ResearchModelRouter(self.controller, self.fx.broker, settings={})

    def build(self, inputs=None, *, cleanup_only=False):
        f = self.fx.f
        if not hasattr(self, "configured"):
            self.configured = True
            self.fx.model = ModelPolicy("moonshotai/Kimi-K3", "2", "10", "0", 1_048_576, 12000,
                f.now-10, f.now+3600, "SYNTHETIC whole-input/output inclusive guaranteed maximum; not production rates",
                allowed_efforts=("medium",), allowed_tools=(), timeout_seconds=900)
            self.fx.models["profiles"] = {"k3_balanced": {"policy": asdict(self.fx.model),
                "max_request_bytes": 4*1024*1024, "billable_input_ceiling": 1_048_576,
                "completion_window": "balanced", "agreement": self.fx.agreement(model=True)}}
            self.fx.model_file = self.fx.rewrite("balanced-models.json", self.fx.models)
            self.fx.inputs = replace(self.fx.inputs, models=self.fx.model_file)
        return build_sail_host_adapters(f.config, inputs=inputs or self.fx.inputs,
            key_source=lambda: self.fail("offline transport must not read a key"),
            box_transport=self.fx.transport, inference_transport=self.native, cleanup_only=cleanup_only,
            poll_monotonic=self.clock, poll_sleep=self.clock.sleep)

    def call(self, key="balanced-original", *, recover=False, **changes):
        self.fx.peer()
        method = self.fx.broker.recover_evaluation if recover else self.fx.broker.evaluate
        values = {"key": key, "effort": "medium", "max_output": 12000, "cache_key": "swarm-rewrite", **changes}
        return method("k3_balanced", [{"role": "system", "content": "stock rewrite system"},
                     {"role": "user", "content": "complete approved history"}], **values)

    def ask(self, key="rewrite-balanced-original"):
        self.fx.peer()
        return self.router.ask(role="rewrite", system="stock rewrite system", user="complete approved history",
            family="swarm", key=key, sail_profile="k3_balanced", effort="medium", max_output=12000)

    def restart(self, *, cleanup_only=False):
        self.fx.adapters = self.build(cleanup_only=cleanup_only)
        self.fx.broker = self.fx.make_broker()
        self.fx.peer()
        self.router = ResearchModelRouter(self.controller, self.fx.broker, settings={})

    def pending(self, *, router=False):
        self.native.gets = [Native.reply("in_progress")]
        self.clock.jump = 901
        with self.assertRaises(ModelError if router else ResearchCapabilityError):
            self.ask() if router else self.call()
        self.clock.jump = None

    def posts(self):
        return [r for r in self.native.calls if r[0] == "POST"]

    def gets(self):
        return [r for r in self.native.calls if r[0] == "GET"]

    def bridge(self):
        return self.fx.adapters.models["k3_balanced"].send.__self__.bridge

    def hold(self):
        return next(iter(self.fx.budget._load()["inference"].values()))

    def test_actual_rewrite_router_preserves_exact_stock_profile_and_wire(self):
        self.native.gets = [Native.reply("in_progress"), Native.reply("completed")]
        answer = self.ask()
        self.assertEqual(answer["json"], {"code": "return []"})
        self.assertEqual(answer["model"], "k3_balanced")
        self.assertIsNone(answer["cost_usd"])
        self.assertEqual(answer["cost_upper_usd"], "2.217152")
        self.assertEqual(answer["cost_status"], "unknown")
        wire = self.posts()[0][2]
        self.assertEqual(wire, {"model": "moonshotai/Kimi-K3", "input": [
            {"role": "system", "content": "stock rewrite system"},
            {"role": "user", "content": "complete approved history"}], "tools": [], "tool_choice": "auto",
            "reasoning": {"effort": "medium"}, "max_output_tokens": 12000, "background": True, "stream": False,
            "truncation": "disabled", "metadata": {"completion_window": "balanced"}, "prompt_cache_key": "swarm-rewrite"})
        self.assertEqual(len(self.gets()), 2)
        self.assertEqual(self.hold()["max_nanos"], 2_217_152_000)
        self.assertIsNone(self.hold()["receipt"])
        held = self.fx.budget._load()["inference"]
        self.restart()
        self.assertEqual(self.ask(), answer)
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 2))
        self.assertEqual(self.controller.spent(["sail_model"]), 0)

    def test_router_timeout_restarts_as_original_get_only_and_keeps_unknown_upper(self):
        self.pending(router=True)
        held = self.fx.budget._load()["inference"]
        accepted = self.bridge().journal("accepted", "model:rewrite-balanced-original")
        self.assertEqual(accepted["response_id"], "resp_balanced-original")
        self.native.gets = [Native.reply("completed")]
        self.restart()
        # Recovery must not count tokens, fetch prices or refresh paid context.
        model = self.fx.broker._models["k3_balanced"]
        self.fx.broker._models["k3_balanced"] = replace(model, count_tokens=lambda body: self.fail("count on recovery"))
        with mock.patch.object(self.bridge(), "fresh", side_effect=AssertionError("fresh paid admission on recovery")):
            response = self.ask()
        self.assertIsNone(response["cost_usd"])
        self.assertEqual(response["cost_upper_usd"], "2.217152")
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 2))
        starts = [json.loads(r["payload"]) for r in self.fx.store._all("SELECT payload FROM events WHERE kind=?", (EVENT_KIND,))]
        self.assertEqual(sum(r["action"] == "request_started" for r in starts), 1)

    def test_each_terminal_status_remains_original_cached_and_never_billed_zero(self):
        for status in ("completed", "incomplete", "failed", "cancelled"):
            with self.subTest(status=status):
                self.native.post = Native.reply(status, incomplete_details={"reason": "max_output_tokens"} if status == "incomplete" else None)
                response = self.call(key="terminal-"+status)
                self.assertEqual(response["status"], status)
                self.assertIsNone(response["cost_usd"])
                self.assertIsNone(response["accrued_day"])
                self.assertEqual(response["cost_upper_usd"], "2.217152")
                self.assertEqual(self.call(key="terminal-"+status, recover=True), response)
        self.assertEqual((len(self.posts()), len(self.gets())), (4, 0))
        self.assertTrue(all(r["receipt"] is None for r in self.fx.budget._load()["inference"].values()))

    def test_failed_and_cancelled_router_recovery_keeps_billed_unknown_evidence(self):
        for status in ("failed", "cancelled"):
            self.native.post = Native.reply(status)
            for _ in range(2):
                with self.subTest(status=status), self.assertRaises(ModelError) as failure:
                    self.ask(key="router-"+status)
                self.assertIsNone(failure.exception.billed[0]["cost_usd"])
                self.assertEqual(failure.exception.billed[0]["cost_upper_usd"], "2.217152")
                self.assertEqual(failure.exception.billed[0]["status"], status)
        self.assertEqual((len(self.posts()), len(self.gets())), (2, 0))

    def test_crash_after_native_terminal_before_broker_cache_recovers_without_any_native_call(self):
        self.native.post = Native.reply("completed")
        original = self.fx.broker._record
        def crash(action, **values):
            if action == "request_finished":
                raise RuntimeError("SYNTHETIC process crash after terminal capture")
            return original(action, **values)
        with mock.patch.object(self.fx.broker, "_record", crash), self.assertRaises(RuntimeError):
            self.call()
        self.assertIsNone(self.fx.broker.cached_result("balanced-original"))
        self.assertEqual(self.bridge().journal("result", "model:balanced-original")["status"], "completed")
        held = self.fx.budget._load()["inference"]
        self.restart()
        answer = self.call(recover=True)
        self.assertEqual(answer["status"], "completed")
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 0))

    def test_crash_immediately_after_durable_acceptance_recovers_original_handle(self):
        model = self.fx.adapters.models["k3_balanced"].send.__self__
        with mock.patch.object(model, "_poll", side_effect=RuntimeError("SYNTHETIC crash after accepted journal")), \
             self.assertRaises(RuntimeError):
            self.call()
        self.restart()
        self.assertEqual(self.call(recover=True)["status"], "completed")
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 1))

    def test_get_timeout_has_persisted_handle_and_recovers_without_new_post(self):
        self.native.gets = [TimeoutError("SYNTHETIC GET timeout")]
        with self.assertRaises(TimeoutError):
            self.call()
        held = self.fx.budget._load()["inference"]
        self.native.gets = [Native.reply("completed")]
        self.restart()
        self.assertEqual(self.call(recover=True)["status"], "completed")
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 2))

    def test_lost_post_ack_without_handle_remains_uncertain_and_cannot_redispatch(self):
        self.native.post = TimeoutError("SYNTHETIC accepted POST with lost acknowledgement")
        with self.assertRaises(TimeoutError):
            self.call()
        held = self.fx.budget._load()["inference"]
        self.restart()
        for recovery in (False, True):
            with self.assertRaisesRegex(ResearchCapabilityError, "accepted response handle is absent"):
                self.call(recover=recovery)
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 0))

    def test_no_original_request_recovery_never_counts_reserves_or_posts(self):
        with self.assertRaisesRegex(ResearchCapabilityError, "original model request is absent"):
            self.call(recover=True)
        self.assertEqual(self.fx.budget._load()["inference"], {})
        self.assertEqual(self.native.calls, [])

    def test_controller_claim_without_broker_dispatch_remains_refused_on_restart(self):
        # A controller claim may commit before its first IPC ever reaches the broker.
        with mock.patch.object(self.fx.broker, "evaluate", side_effect=TimeoutError("SYNTHETIC IPC lost before dispatch")), \
             self.assertRaises(ModelError):
            self.ask()
        self.restart()
        with self.assertRaises(ModelError):
            self.ask()
        self.assertEqual(self.native.calls, [])
        self.assertEqual(self.fx.budget._load()["inference"], {})

    def test_changed_body_options_and_profile_refuse_before_get_or_post(self):
        self.pending()
        before = list(self.native.calls)
        for change in ({"cache_key": "swarm-architect"}, {"tool_choice": "none"}, {"max_output": 11999}):
            with self.subTest(change=change), self.assertRaisesRegex(ResearchCapabilityError, "different work"):
                self.call(recover=True, **change)
        self.assertEqual(self.native.calls, before)
        rows = json.loads(json.dumps(self.fx.models))
        rows["profiles"]["k3_balanced"]["completion_window"] = "asap"
        receipt = self.fx.rewrite("wrong-window.json", rows)
        with self.assertRaisesRegex(ResearchCapabilityError, "stock Sail profile"):
            self.build(replace(self.fx.inputs, models=receipt))
        rows["profiles"]["k3_balanced"]["completion_window"] = "balanced"
        rows["profiles"]["k3_balanced"]["policy"]["model"] = "zai-org/GLM-5.3"
        receipt = self.fx.rewrite("wrong-model.json", rows)
        with self.assertRaisesRegex(ResearchCapabilityError, "stock Sail profile"):
            self.build(replace(self.fx.inputs, models=receipt))
        self.assertEqual(self.native.calls, before)

    def test_foreign_scope_cannot_retrieve_the_original_handle(self):
        self.pending()
        before = list(self.native.calls)
        foreign = replace(self.fx.f.policy, scope="synthetic-foreign-scope")
        self.fx.broker.policy = foreign
        with self.assertRaisesRegex(ResearchCapabilityError, "scope or reviewed policy changed"):
            self.call(recover=True)
        self.assertEqual(self.native.calls, before)

    def test_foreign_get_handle_is_archived_refused_and_original_handle_never_replaced(self):
        self.pending()
        original = self.bridge().journal("accepted", "model:balanced-original")
        self.native.gets = [Native.reply("completed", id="resp_foreign")]
        with self.assertRaisesRegex(ResearchCapabilityError, "response handle changed"):
            self.call(recover=True)
        self.assertEqual(self.bridge().journal("accepted", "model:balanced-original"), original)
        self.assertIsNone(self.hold()["receipt"])
        self.native.gets = [Native.reply("completed")]
        self.assertEqual(self.call(recover=True)["id"], "resp_balanced-original")
        self.assertEqual(len(self.posts()), 1)
        self.assertTrue(all(r[1] == "/v1/responses/resp_balanced-original" for r in self.gets()))

    def test_accepted_receipt_corruption_refuses_without_native_call(self):
        self.pending()
        rows = [json.loads(r["payload"]) for r in self.fx.store._all("SELECT payload FROM events WHERE kind=?", (HOST_EVENT,))]
        accepted = next(r for r in rows if r["action"] == "sail_bridge_accepted")
        path = self.fx.f.broker_root / "sail-bridge-results" / (accepted["sha256"]+".json")
        path.write_text('{}')
        before = list(self.native.calls)
        self.restart()
        with self.assertRaisesRegex(ResearchCapabilityError, "receipt bytes changed"):
            self.call(recover=True)
        self.assertEqual(self.native.calls, before)

    def test_invalid_accepted_model_status_or_absent_id_is_not_replayed(self):
        # Each invalid answer is still potential liability, with immutable observation evidence.
        for i, change in enumerate(({"model": "zai-org/GLM-5.3"}, {"status": "invented"}, {"id": None})):
            self.native.post = Native.reply("queued", **change)
            with self.subTest(change=change), self.assertRaises(ResearchCapabilityError):
                self.call(key="invalid-"+str(i))
            with self.subTest(change=change), self.assertRaises(ResearchCapabilityError):
                self.call(key="invalid-"+str(i), recover=True)
        self.assertEqual((len(self.posts()), len(self.gets())), (3, 0))
        self.assertTrue(all(r["receipt"] is None for r in self.fx.budget._load()["inference"].values()))

    def test_default_legacy_capability_refuses_unresolved_even_with_native_handle(self):
        self.pending()
        old = self.fx.broker._models["k3_balanced"]
        self.fx.broker._models["k3_balanced"] = ModelCapability(old.policy, old.count_tokens, old.send)
        before = list(self.native.calls)
        with self.assertRaisesRegex(ResearchCapabilityError, "no redispatch"):
            self.call(recover=True)
        self.assertEqual(self.native.calls, before)

    def test_persisted_foreign_handle_and_wire_refuse_before_any_get(self):
        self.pending()
        bridge = self.bridge()
        journal = bridge.journal
        accepted = journal("accepted", "model:balanced-original")
        intent = journal("intent", "model:balanced-original")
        before = list(self.native.calls)
        for action, forged in (("accepted", {**accepted, "response_id": "resp_foreign"}),
                               ("accepted", {**accepted, "body_sha256": "b"*64}),
                               ("intent", {**intent, "wire_sha256": "b"*64})):
            def changed(kind, key, document=None, **kw):
                if kind == action and document is None:
                    return forged
                return journal(kind, key, document, **kw)
            with self.subTest(action=action, forged=forged), mock.patch.object(bridge, "journal", changed), \
                 self.assertRaises(ResearchCapabilityError):
                self.call(recover=True)
        self.assertEqual(self.native.calls, before)
        self.assertEqual(journal("accepted", "model:balanced-original"), accepted)
        self.assertEqual(journal("intent", "model:balanced-original"), intent)

    def test_repeated_pending_and_expired_native_result_keep_the_same_hold_and_failure_history(self):
        self.pending()
        held = self.fx.budget._load()["inference"]
        history = [tuple(r) for r in self.fx.store._all("SELECT seq,kind,payload FROM events ORDER BY seq")]
        self.clock.jump = 901
        with self.assertRaisesRegex(ResearchCapabilityError, "remains pending"):
            self.call(recover=True)
        self.clock.jump = None
        self.native.gets = [RuntimeError("SYNTHETIC native 404 after result retention expiry")]
        with self.assertRaises(RuntimeError):
            self.call(recover=True)
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertEqual([tuple(r) for r in self.fx.store._all("SELECT seq,kind,payload FROM events ORDER BY seq")][:len(history)], history)
        self.assertEqual(len(self.posts()), 1)
        self.assertIsNone(self.fx.broker.cached_result("balanced-original"))

    def test_nonadvancing_clock_still_has_finite_poll_bound(self):
        self.native.gets = [Native.reply("in_progress")]
        self.clock.sleep = lambda seconds: None
        model = self.fx.adapters.models["k3_balanced"].send.__self__
        model.sleep = self.clock.sleep
        with self.assertRaisesRegex(ResearchCapabilityError, "remains pending"):
            self.call()
        self.assertEqual(len(self.gets()), 451)
        self.assertEqual(len(self.posts()), 1)
        self.assertIsNone(self.hold()["receipt"])

    def test_concurrent_passive_pollers_commit_one_original_terminal_cache(self):
        self.pending()
        held = self.fx.budget._load()["inference"]
        barrier = threading.Barrier(2)
        transport = self.native
        def synchronized(method, path, body=None, **kw):
            if method == "GET":
                barrier.wait(5)
            return transport(method, path, body, **kw)
        self.native.gets = [Native.reply("completed")]
        model = self.fx.adapters.models["k3_balanced"].send.__self__
        model.transport = synchronized
        results, errors = [], []
        def poll():
            try:
                results.append(self.call(recover=True))
            except BaseException as exc:
                errors.append(exc)
        threads = [threading.Thread(target=poll) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(8)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.fx.budget._load()["inference"], held)
        events = [json.loads(r["payload"]) for r in self.fx.store._all("SELECT payload FROM events WHERE kind=?", (EVENT_KIND,))]
        self.assertEqual(sum(r["action"] == "request_started" for r in events), 1)
        self.assertEqual(sum(r["action"] == "request_finished" for r in events), 1)
        self.assertEqual(len(self.posts()), 1)

    def test_original_hold_is_checked_before_recovery_callback(self):
        self.pending()
        called = []
        model = self.fx.broker._models["k3_balanced"]
        self.fx.broker._models["k3_balanced"] = replace(model, recover=lambda body: called.append(body))
        original = self.fx.budget._load
        def lost():
            state = original()
            state["inference"] = {}
            return state
        with mock.patch.object(self.fx.budget, "_load", lost), self.assertRaisesRegex(ResearchCapabilityError, "original dispatched reservation"):
            self.call(recover=True)
        self.assertEqual(called, [])
        self.assertEqual(len(self.posts()), 1)

    def test_actual_invoice_already_settled_after_crash_is_not_settled_twice(self):
        self.pending()
        key = "balanced-original"
        daily_key = "model-" + hashlib.sha256((self.fx.f.policy.scope+":"+key).encode()).hexdigest()
        day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        self.fx.budget.settle_inference(daily_key, actual_usd="0.25", accrued_day=day,
                                       provenance="SYNTHETIC original independently reconciled invoice")
        self.native.gets = [Native.reply("completed")]
        original = self.bridge().terminal_bill
        def invoice(request_key, response, native_model, body_sha):
            self.fx.actual_bill = self.fx.rewrite("SYNTHETIC-recovered-known-invoice.json", {"schema": 1,
                "scope": self.fx.f.policy.scope, "request_key": request_key, "response_id": response,
                "model": native_model, "body_sha256": body_sha, "actual_usd": "0.25", "accrued_day": day,
                "final": True, "provenance": "SYNTHETIC original reconciled invoice"})
            return original(request_key, response, native_model, body_sha)
        with mock.patch.object(self.bridge(), "terminal_bill", invoice):
            result = self.call(recover=True)
        self.assertEqual((result["cost_usd"], result["accrued_day"], result["cost_status"]), ("0.25", day, "vendor_actual"))
        self.assertEqual(result["cost_upper_usd"], "2.217152")
        self.assertEqual(self.hold()["receipt"]["actual_nanos"], 250_000_000)
        self.assertEqual(len(self.posts()), 1)

    def test_noncallable_recovery_capability_is_not_admitted(self):
        original = self.fx.adapters.models["k3_balanced"]
        self.fx.adapters.models["k3_balanced"] = replace(original, recover=object())
        try:
            with self.assertRaisesRegex(ResearchCapabilityError, "invalid host model capabilities"):
                self.fx.make_broker()
        finally:
            self.fx.adapters.models["k3_balanced"] = original
        self.assertEqual(self.native.calls, [])

    def test_closed_and_cleanup_only_admission_allows_only_passive_original_recovery(self):
        self.pending()
        self.fx.broker._closed_reply("SYNTHETIC owner withdrawal")
        self.native.gets = [Native.reply("completed")]
        self.restart(cleanup_only=True)
        answer = self.call(recover=True)
        self.assertEqual(answer["status"], "completed")
        self.assertTrue(self.fx.broker._load()["closed"])
        self.assertEqual(len(self.posts()), 1)
        with self.assertRaises(ResearchCapabilityError):
            self.call(key="new-after-withdrawal")
        self.assertEqual(len(self.posts()), 1)

    def test_price_expiry_and_midnight_do_not_reprice_release_or_redispatch_original_hold(self):
        self.pending()
        held = self.fx.budget._load()["inference"]
        future = self.fx.f.now + 86400
        self.fx.store.clock = lambda: future
        self.native.gets = [Native.reply("completed")]
        # Recovery deliberately uses the original immutable receipts, not tomorrow's rates.
        self.fx.adapters = build_sail_host_adapters(self.fx.f.config, inputs=self.fx.inputs,
            key_source=lambda: self.fail("key read"), box_transport=self.fx.transport, inference_transport=self.native,
            cleanup_only=True, clock=lambda: future, poll_monotonic=self.clock, poll_sleep=self.clock.sleep)
        self.fx.broker = self.fx.make_broker()
        original_proof = self.fx.broker._verify
        self.fx.broker._verify = lambda peer, **kw: replace(original_proof(peer, **kw), observed_at=future, valid_until=future+60)
        response = self.call(recover=True)
        self.assertIsNone(response["cost_usd"])
        self.assertIsNone(response["accrued_day"])
        self.assertEqual(self.fx.budget._load()["inference"], held)
        self.assertIsNone(self.hold()["receipt"])
        self.assertEqual(self.hold()["max_nanos"], 2_217_152_000)
        with self.assertRaises(DailyAdmissionError):
            self.fx.budget.summary()  # Tomorrow's paid admission needs genuinely fresh inventory.
        self.assertEqual(len(self.posts()), 1)

    def test_known_over_bound_terminal_invoice_commits_breach_and_blocks_new_admission(self):
        self.native.post = Native.reply("completed")
        model = self.fx.adapters.models["k3_balanced"].send.__self__
        original_bill = model.bridge.terminal_bill
        def bill(key, response, native_model, body_sha):
            self.fx.actual_bill = self.fx.rewrite("SYNTHETIC-over-bound-invoice.json", {"schema": 1,
                "scope": self.fx.f.policy.scope, "request_key": key, "response_id": response, "model": native_model,
                "body_sha256": body_sha, "actual_usd": "3", "accrued_day": dt.datetime.now(dt.timezone.utc).date().isoformat(),
                "final": True, "provenance": "SYNTHETIC authoritative over-bound invoice"})
            return original_bill(key, response, native_model, body_sha)
        with mock.patch.object(model.bridge, "terminal_bill", bill), self.assertRaises(DailyAdmissionError):
            self.call()
        self.assertTrue(self.fx.budget._load()["breached"])
        self.assertIsNone(self.fx.broker.cached_result("balanced-original"))
        self.restart(cleanup_only=True)
        self.assertTrue(self.fx.budget._load()["breached"])
        with self.assertRaises((ResearchCapabilityError, DailyAdmissionError)):
            self.call(key="new-after-breach")
        self.assertEqual(len(self.posts()), 1)

    def test_policy_output_effort_tool_and_payload_bounds_remain_before_paid_post(self):
        for change in ({"max_output": 12001}, {"effort": "high"}, {"tools": [{"type": "web_search"}]}):
            with self.subTest(change=change), self.assertRaises(ResearchCapabilityError):
                self.call(**change)
        with self.assertRaises(ResearchCapabilityError):
            self.fx.broker.evaluate("k3_balanced", [{"role": "user", "content": "x"*(4*1024*1024)}],
                key="oversize", effort="medium", max_output=12000)
        self.assertEqual(self.native.calls, [])
        self.assertEqual(self.fx.budget._load()["inference"], {})

    def test_authenticated_ipc_recovery_operation_cannot_dispatch_a_missing_original(self):
        path = self.fx.f.broker_root / "balanced-test.sock"
        listener = create_listener(path)
        self.addCleanup(listener.close)
        self.addCleanup(path.unlink, missing_ok=True)
        server = BrokerServer(self.fx.broker, controller_uid=os.getuid())
        failures = []
        def serve():
            try:
                conn, _ = listener.accept()
                with conn:
                    server.serve_connection(conn)
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=serve)
        thread.start()
        client = BrokerClient(path, broker_uid=os.getuid(), timeout=5)
        with self.assertRaises(Exception):
            client.recover_evaluation("k3_balanced", [{"role": "user", "content": "no original"}],
                                     key="no-original-ipc", effort="medium", max_output=12000)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.native.calls, [])

    def test_authenticated_ipc_recovery_retrieves_only_the_persisted_accepted_handle(self):
        self.pending()
        self.native.gets = [Native.reply("completed")]
        path = self.fx.f.broker_root / "balanced-recovery.sock"
        listener = create_listener(path)
        self.addCleanup(listener.close)
        self.addCleanup(path.unlink, missing_ok=True)
        server = BrokerServer(self.fx.broker, controller_uid=os.getuid())
        errors = []
        def serve():
            try:
                conn, _ = listener.accept()
                with conn:
                    server.serve_connection(conn)
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve)
        thread.start()
        client = BrokerClient(path, broker_uid=os.getuid(), timeout=5)
        answer = client.recover_evaluation("k3_balanced", [{"role": "system", "content": "stock rewrite system"},
            {"role": "user", "content": "complete approved history"}], key="balanced-original",
            effort="medium", max_output=12000, cache_key="swarm-rewrite")
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(answer["status"], "completed")
        self.assertIsNone(answer["cost_usd"])
        self.assertEqual((len(self.posts()), len(self.gets())), (1, 2))

if __name__ == "__main__":
    unittest.main()

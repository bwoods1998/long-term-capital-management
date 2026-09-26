"""Paid dispatch boundaries, using the real Frontier client and fake HTTP responses."""

import copy
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.frontier import Frontier
from league.swarm.models import ModelError, ModelRouter
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeMonth
from league.tests.test_frontier import FakeOpener, GATEWAY, http_error, ok


class SwarmFrontierRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        self.month = FakeMonth(1000)
        self.sail_calls = []

    def router(self, opener, *, store=None):
        router = ModelRouter(store or self.store, None, settings=self.settings, month=self.month,
                             frontier_factory=lambda model: Frontier(GATEWAY, lambda: "synthetic", model=model,
                                                                     opener=opener))

        def sail(*args, **kwargs):
            self.sail_calls.append(kwargs)
            return SimpleNamespace(output_text='{"fallback":true}', cost_usd=Decimal("0.02"))

        router.sail = sail
        return router

    def ask(self, router, **kw):
        args = dict(role="architect", system="synthetic", user="packet", family=None, key="synthetic-call",
                    openai_model="gpt-6-astra", sail_profile="pro_balanced", max_output=6000, need_usd=0.01)
        args.update(kw)
        return router.ask(**args)

    @staticmethod
    def standard_minimum(opener):
        # Independent calculation against the current gateway's Astra long-context rates.
        body = opener.body()
        return (Decimal(len(opener.request.data) + 4096) * 25 + Decimal(body["max_output_tokens"]) * 75) / 1000000

    def test_each_role_reaches_its_intended_tier_and_attribution(self):
        for role, tier in (("architect", "flex"), ("review", "flex"), ("postmortem", "flex"), ("audit", "default")):
            with self.subTest(role=role):
                opener = FakeOpener(ok(service_tier=tier))
                result = self.ask(self.router(opener), role=role, key=role)
                self.assertEqual(result["route"], "openai")
                self.assertEqual(opener.body()["service_tier"], tier)
                self.assertEqual(opener.headers()["x-ltcm-role"], role)
                self.assertEqual(result["service_tier"], tier)

    def test_only_postmortem_can_reach_the_existing_64000_output_ceiling(self):
        for role, expected in (("postmortem", 64000), ("architect", 16000), ("audit", 16000)):
            opener = FakeOpener(ok())
            self.ask(self.router(opener), role=role, max_output=100000)
            self.assertEqual(opener.body()["max_output_tokens"], expected)

    def test_request_that_exceeds_remaining_budget_falls_back_before_dispatch(self):
        self.settings["guard"]["openai_cap_usd"] = 2
        opener = FakeOpener(ok())
        result = self.ask(self.router(opener), user="x" * 100000, max_output=64000, role="postmortem")
        self.assertEqual(result["route"], "sail")
        self.assertEqual(opener.calls, [])
        self.assertEqual(self.store.spent(["openai"]), 0)

    def test_unknown_cost_keeps_the_full_request_hold_and_is_not_reported_free(self):
        opener = FakeOpener(ok(cost=None, service_tier="flex"))
        result = self.ask(self.router(opener), role="postmortem", max_output=64000)
        self.assertGreaterEqual(Decimal(str(self.store.spent(["openai"]))), self.standard_minimum(opener))
        self.assertFalse(result["cost_verified"])
        self.assertIsNone(result["cost_usd"])
        self.assertGreater(result["held_usd"], 4.8)

    def test_timeout_keeps_the_full_request_hold_across_reopening_the_store(self):
        opener = FakeOpener(TimeoutError("synthetic timeout"))
        result = self.ask(self.router(opener), role="postmortem", max_output=64000)
        self.assertEqual(result["route"], "sail")
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        self.assertGreaterEqual(Decimal(str(other.spent(["openai"]))), self.standard_minimum(opener))
        self.assertEqual(len(opener.calls), 1)

    def test_flex_429_releases_hold_then_uses_sail_once(self):
        refusal = http_error(429, "synthetic resource unavailable")
        self.addCleanup(refusal.close)
        opener = FakeOpener(refusal)
        result = self.ask(self.router(opener))
        self.assertEqual(result["route"], "sail")
        self.assertEqual(self.store.spent(["openai"]), 0)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(len(self.sail_calls), 1)

    def test_verified_cost_settles_exactly_and_records_the_actual_tier(self):
        opener = FakeOpener(ok(cost="0.0421", service_tier="default"))
        result = self.ask(self.router(opener), role="postmortem", max_output=64000)
        self.assertAlmostEqual(self.store.spent(["openai"]), 0.0421)
        self.assertTrue(result["cost_verified"])
        self.assertEqual(result["service_tier"], "default", "requesting flex does not prove flex service")
        self.assertEqual(result["held_usd"], 0)

    def test_concurrent_dispatches_share_the_same_remaining_allowance(self):
        self.settings["guard"]["openai_cap_usd"] = 5.0
        entered, release = threading.Event(), threading.Event()
        failures = []
        opener = FakeOpener(ok(cost="0.04"))

        def waiting(request, timeout=None):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test did not release the first response")
            return opener(request, timeout=timeout)

        first = self.router(waiting)
        other_store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other_store.close)
        second_opener = FakeOpener(ok())
        second = self.router(second_opener, store=other_store)

        def run_first():
            try:
                self.ask(first, role="postmortem", max_output=64000, key="first")
            except Exception as exc:
                failures.append(exc)

        worker = threading.Thread(target=run_first)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            result = self.ask(second, role="postmortem", max_output=64000, key="second")
            self.assertEqual(result["route"], "sail")
            self.assertEqual(second_opener.calls, [])
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    def test_failed_hold_commit_cannot_reach_the_paid_endpoint(self):
        atomic = self.store.atomic

        @contextmanager
        def fail_commit():
            with atomic():
                yield
                raise sqlite3.OperationalError("synthetic disk-full commit failure")

        self.store.atomic = fail_commit
        opener = FakeOpener(ok())
        result = self.ask(self.router(opener))
        self.assertEqual(result["route"], "sail")
        self.assertEqual(opener.calls, [])
        self.assertEqual(self.store.spent(["openai"]), 0)

    def test_unreadable_or_nonfinite_budget_never_dispatches_openai(self):
        for field, value in (("openai_cap_usd", "NaN"), ("openai_cap_usd", "Infinity"),
                             ("openai_cap_usd", True), ("openai_reserve_usd", -1),
                             ("openai_reserve_usd", "NaN")):
            with self.subTest(field=field, value=value):
                old = self.settings["guard"][field]
                try:
                    self.settings["guard"][field] = value
                    opener = FakeOpener(ok())
                    self.assertEqual(self.ask(self.router(opener))["route"], "sail")
                    self.assertEqual(opener.calls, [])
                finally:
                    self.settings["guard"][field] = old
        for amount in (None, "NaN", "Infinity"):
            self.month.value = amount
            opener = FakeOpener(ok())
            self.assertEqual(self.ask(self.router(opener))["route"], "sail")
            self.assertEqual(opener.calls, [])

    def test_caller_transaction_cannot_turn_a_pending_hold_into_paid_dispatch(self):
        opener = FakeOpener(ok())
        with self.store.atomic():
            with self.assertRaisesRegex(ModelError, "uncommitted"):
                self.ask(self.router(opener))
        self.assertEqual(opener.calls, [])
        self.assertEqual(self.sail_calls, [])
        self.assertEqual(self.store.spent(["openai"]), 0)

    def test_failure_from_sqlite_commit_itself_rolls_back_before_fallback(self):
        def deny_commit(action, first, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT" else sqlite3.SQLITE_OK

        self.store._db.set_authorizer(deny_commit)
        opener = FakeOpener(ok())
        router = self.router(opener)
        original = router.sail
        transactions_seen = []

        def observed_sail(*args, **kwargs):
            transactions_seen.append(self.store._db.in_transaction)
            return original(*args, **kwargs)

        router.sail = observed_sail
        self.assertEqual(self.ask(router)["route"], "sail")
        self.assertEqual(opener.calls, [])
        self.assertEqual(transactions_seen, [False])
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        self.assertEqual(other.spent(["openai"]), 0)
        self.store._db.set_authorizer(None)

    def test_failed_commit_and_failed_rollback_abort_both_paid_routes(self):
        def deny_finish(action, first, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first in ("COMMIT", "ROLLBACK") else sqlite3.SQLITE_OK

        self.store._db.set_authorizer(deny_finish)
        opener = FakeOpener(ok())
        with self.assertRaisesRegex(ModelError, "readable budget store"):
            self.ask(self.router(opener))
        self.assertEqual(opener.calls, [])
        self.assertEqual(self.sail_calls, [])
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        self.assertEqual(other.spent(["openai"]), 0)


if __name__ == "__main__":
    unittest.main()

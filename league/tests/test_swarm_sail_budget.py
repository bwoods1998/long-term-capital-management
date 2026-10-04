"""Sail model admission against the owner's research ceiling. Real ledgers and Provider; scripted transport only."""
from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.models import ModelError, ModelRouter
from league.swarm.store import SwarmStore
from ltcm.provider import Provider, ProviderError, PROFILES, TransportError
from ltcm.tests.test_provider import FakeTransport, message, response


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 10, 5, 23, 59, tzinfo=dt.timezone.utc).timestamp()

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class SailBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.write_budget()
        with patch("time.time", self.clock):
            self.settings = S.load(self.root, config={})

    def write_budget(self, sail_balance=500):
        inputs = {"p30_usd": 0.0, "edge": {"stop": False}, "meters": {
            "sail": {"balance_usd": sail_balance, "fixed_usd_day": 1.0, "reserve_usd": 37.0},
            "claude": {"balance_usd": 500.0, "fixed_usd_day": 0.0}}}
        B._write_json(self.root / "budget.json", B.compute(inputs, now=self.clock()))

    @staticmethod
    def answer():
        return response(rid="resp_sail_budget", model=PROFILES["k3_balanced"][0], output=[message("{}")],
                        usage={"input_tokens": 1000, "output_tokens": 6000,
                               "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {},
                               "total_tokens": 7000})

    def router(self, transport, *, store=None):
        provider = Provider(self.root / "provider.sqlite", transport=transport, clock=self.clock,
                            floor_cap_usd_per_day="150", sleep=lambda seconds: None)
        self.addCleanup(provider.close)
        return ModelRouter(store or self.store, provider, settings=self.settings, sleep=lambda seconds: None)

    def ask(self, router, key="request", *, role="audit", **kwargs):
        args = {"family": "synthetic:audit", "key": key, "max_output": 6000,
                "role": role, "cap_usd_day": 1.0}
        args.update(kwargs)
        return router.sail("k3_balanced", [{"role": "user", "content": "synthetic"}], **args)

    def today_spent(self):
        now = self.clock()
        return self.store.spent(B.SAIL_KINDS, since=now - now % 86400)

    def test_gate_call_that_would_cross_the_owner_cap_never_dispatches(self):
        self.store.add_spend("gym_box", 14.99)
        self.store.add_spend("claude", 10.0)
        transport = FakeTransport()
        with self.assertRaisesRegex(ModelError, "Sail research budget"):
            self.ask(self.router(transport))
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.today_spent(), 14.99)
        self.assertEqual(self.store.spent(["claude"]), 10.0)
        self.assertFalse(self.store.get("unsettled"))

    def test_two_connections_cannot_reserve_the_same_remaining_room(self):
        self.store.add_spend("gym_box", 14.92)  # enough for one conservative $0.068... hold, less than two
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        started, release, refused = threading.Event(), threading.Event(), threading.Event()
        posts = []

        def transport(method, route, body=None, idempotency_key=None):
            posts.append(idempotency_key)
            started.set()
            if not release.wait(3):
                raise AssertionError("the offline test did not release its scripted response")
            return self.answer()

        routers = [self.router(transport), self.router(transport, store=other)]
        barrier = threading.Barrier(3)
        results = []

        def worker(index):
            barrier.wait()
            try:
                self.ask(routers[index], key=f"concurrent-{index}")
                results.append("answered")
            except ModelError:
                results.append("refused")
                refused.set()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        try:
            self.assertTrue(started.wait(3))
            self.assertTrue(refused.wait(3))
            self.assertEqual(len(posts), 1)
            self.assertLessEqual(self.today_spent(), 15.0)
        finally:
            release.set()
            for thread in threads:
                thread.join(3)
        self.assertEqual(sorted(results), ["answered", "refused"])
        self.assertAlmostEqual(self.today_spent(), 14.982, places=6)

    def test_non_gate_roles_leave_the_sail_gate_reserve(self):
        self.store.add_spend("gym_box", 13.49)
        transport = FakeTransport(self.answer())
        router = self.router(transport)
        with self.assertRaises(ModelError):
            self.ask(router, key="research", role="researcher")
        self.assertEqual(transport.calls, [])
        self.ask(router, key="gate", role="audit")
        self.assertEqual(len(transport.posts), 1)

    def test_unknown_pricing_and_uncommitted_holds_never_dispatch(self):
        transport = FakeTransport()
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            router.sail("unpriced-model", [{"role": "user", "content": "synthetic"}], family="f", key="unknown")
        with self.store.atomic():
            with self.assertRaisesRegex(ModelError, "uncommitted"):
                self.ask(router)
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.today_spent(), 0)

    def test_root_budget_cut_tightens_an_existing_settings_snapshot(self):
        self.write_budget(sail_balance=37.0)
        self.assertEqual(self.settings["budget"]["sail_usd_day"], 15.0)
        transport = FakeTransport()
        with self.assertRaises(ModelError):
            self.ask(self.router(transport))
        self.assertEqual(transport.calls, [])

    def test_local_provider_refusal_releases_the_pre_dispatch_hold(self):
        transport = FakeTransport(self.answer())
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(router, cap_usd_day=0.0)
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.today_spent(), 0)
        self.assertFalse(self.store.get("unsettled"))
        self.ask(router)
        self.assertAlmostEqual(self.today_spent(), 0.062, places=6)

    def test_cached_response_needs_no_new_room_and_books_no_second_cost(self):
        transport = FakeTransport(self.answer())
        router = self.router(transport)
        self.ask(router)
        self.store.add_spend("gym_box", 15.0 - self.today_spent())
        self.ask(router)
        self.assertEqual(len(transport.posts), 1)
        self.assertAlmostEqual(self.today_spent(), 15.0, places=9)

    def test_answer_after_midnight_settles_only_its_original_day(self):
        def transport(method, route, body=None, idempotency_key=None):
            self.clock.advance(120)
            self.store.add_spend("gym_box", 1.0)
            return self.answer()

        router = self.router(transport)
        self.ask(router)
        self.assertAlmostEqual(self.today_spent(), 1.0, places=9)
        self.assertAlmostEqual(self.store.spent(B.SAIL_KINDS), 1.062, places=6)
        self.assertFalse(self.store.get("unsettled"))

    def test_unknown_bill_survives_restart_and_retry_settles_once(self):
        transport = FakeTransport(TransportError("provider_transport_unconfirmed"), self.answer())
        first = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(first)
        held = self.today_spent()
        self.assertGreater(held, 0.062)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        restarted = self.router(transport, store=other)
        self.ask(restarted)
        self.ask(restarted)
        self.assertEqual(len(transport.posts), 2)  # one uncertain POST, then the same Provider idempotency key
        self.assertAlmostEqual(self.today_spent(), 0.062, places=6)
        self.assertFalse(other.get("unsettled"))

    def test_released_old_day_request_cannot_move_to_a_fresh_day(self):
        transport = FakeTransport(ProviderError("provider_http_400"))
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(router)
        self.assertEqual(self.today_spent(), 0)
        self.clock.advance(120)
        self.write_budget()
        with self.assertRaisesRegex(ModelError, "UTC budget day"):
            self.ask(router)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(self.today_spent(), 0)

    def test_late_answer_after_a_release_retains_the_original_accounting_day(self):
        router = self.router(FakeTransport())
        router._sail_admit("late", 0.1, kind="sail_model", family=None, profile="k3_balanced", role="audit")
        router._account_sail("late", 0.0, kind="sail_model", family=None, settled=True, released=True, detail={})
        self.clock.advance(120)
        self.store.add_spend("gym_box", 1.0)
        router._account_sail("late", 0.062, kind="sail_model", family=None, settled=True, detail={})
        self.assertAlmostEqual(self.today_spent(), 1.0, places=9)
        self.assertAlmostEqual(self.store.spent(B.SAIL_KINDS), 1.062, places=6)

    def test_pre_dispatch_crash_hold_is_repriced_before_a_larger_retry(self):
        transport = FakeTransport()
        router = self.router(transport)
        router._sail_admit("grown", 0.01, kind="sail_model", family=None, profile="k3_balanced", role="audit")
        self.store.add_spend("gym_box", 14.97)
        with self.assertRaises(ModelError):
            self.ask(router, key="grown")  # the actual request requires more than its old $0.01 hold
        self.assertEqual(transport.calls, [])
        self.assertAlmostEqual(self.today_spent(), 14.98, places=9)

    def test_released_retry_with_smaller_new_body_reserves_the_original_body_before_dispatch(self):
        transport = FakeTransport(ProviderError("provider_http_400"), self.answer())
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(router)  # the durable body needs 6000 output tokens
        self.assertEqual(self.today_spent(), 0)
        self.store.add_spend("gym_box", 14.97)
        with self.assertRaisesRegex(ModelError, "Sail research budget"):
            self.ask(router, max_output=16)  # Provider would replay the original larger body on this key
        self.assertEqual(len(transport.posts), 1)
        self.assertAlmostEqual(self.today_spent(), 14.97, places=9)
        self.assertFalse(self.store.get("unsettled"))

    def test_released_retry_with_unknown_original_price_never_dispatches(self):
        transport = FakeTransport(ProviderError("provider_http_400"), self.answer())
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(router)
        router.provider._db.execute("UPDATE requests SET reserved_usd='NaN'")
        with self.assertRaisesRegex(ModelError, "original request has no conservative price"):
            self.ask(router, max_output=16)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(self.today_spent(), 0)
        self.assertFalse(self.store.get("unsettled"))

    def test_unreadable_provider_record_cannot_price_a_released_retry_as_a_new_body(self):
        transport = FakeTransport(ProviderError("provider_http_400"), self.answer())
        router = self.router(transport)
        with self.assertRaises(ProviderError):
            self.ask(router)
        self.store.add_spend("gym_box", 14.97)
        unreadable = Mock()
        unreadable.execute.side_effect = sqlite3.OperationalError("synthetic unreadable request store")
        with patch.object(router.provider, "_db", unreadable):
            with self.assertRaisesRegex(ModelError, "original request record cannot be read"):
                self.ask(router, max_output=16)
        self.assertEqual(len(transport.posts), 1)
        self.assertAlmostEqual(self.today_spent(), 14.97, places=9)
        self.assertFalse(self.store.get("unsettled"))

    def test_missing_provider_cache_cannot_make_a_new_dispatch_free(self):
        transport = FakeTransport(self.answer())
        router = self.router(transport)
        self.ask(router)
        router.provider._db.execute("DELETE FROM requests")  # simulate losing the provider's cache after settlement
        self.store.add_spend("gym_box", 15.0 - self.today_spent())
        with self.assertRaisesRegex(ModelError, "terminal Provider record"):
            self.ask(router)
        self.assertEqual(len(transport.posts), 1)
        self.assertAlmostEqual(self.today_spent(), 15.0, places=9)


if __name__ == "__main__":
    unittest.main()

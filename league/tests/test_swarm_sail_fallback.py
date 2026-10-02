"""The Sail window fallback (V3-A, Oct 2, 2026; league/swarm/models.py THE WINDOW FALLBACK). Sail's balanced queue
stalled 07:00-12:53Z and the architect bore nothing for six hours: a one-shot call on a profile outside the asap window
that `sail_fallback` maps now retries once on the asap profile after a poll timeout, flags the window for an hour (one
alert a stall), and while the flag stands goes straight to the fallback. A fake Provider; every answer is invented."""

from __future__ import annotations

import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.swarm import settings as S
from league.swarm.models import STALL_KEY, STALL_SECONDS, ModelError, ModelRouter, asap_twin, fallback_key
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from ltcm.provider import ProviderError, model_of, window_of


class FakeProvider:
    """`respond` as the Provider's: a poll timeout for every profile of a stalled window, else an answer."""

    def __init__(self, stalled=("balanced",), error="provider_poll_timeout"):
        self.stalled = set(stalled)
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def respond(self, profile, items, *, request_key, **kw):
        self.calls.append((profile, request_key))
        if window_of(profile) in self.stalled:
            raise ProviderError(self.error)
        return SimpleNamespace(output_text='{"families": []}', cost_usd=Decimal("0.02"), incomplete=False,
                               incomplete_reason=None, usage={"output_tokens": 12})


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.provider = FakeProvider()
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings, sleep=lambda s: None)

    def ask(self, profile="k3_balanced", key="arch-1", role="architect"):
        return self.router.ask(role=role, system="system", user="user", family=None, key=key, openai_model=None,
                               sail_profile=profile, max_output=4000, effort="medium")

    def alerts(self):
        return [e["payload"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.status" and e["payload"].get("action") == "sail_window_stall"]


class TheFallback(Case):
    def test_a_poll_timeout_retries_once_on_the_asap_profile_with_a_new_key_and_flags_the_window(self):
        answer = self.ask()
        self.assertEqual(self.provider.calls, [("k3_balanced", "arch-1"), ("pro_asap", fallback_key("arch-1", "pro_asap"))])
        self.assertNotEqual(fallback_key("arch-1", "pro_asap"), "arch-1")
        self.assertEqual((answer["route"], answer["model"], answer["json"]), ("sail", "pro_asap", {"families": []}))
        self.assertEqual(answer["sail_fallback"], {"from": "k3_balanced", "to": "pro_asap", "why": "stall"})
        self.assertIn("provider_poll_timeout", answer["fallback_reasons"][0])
        flag = self.store.get(STALL_KEY)["balanced"]
        self.assertEqual((flag["until"], flag["since"], flag["profile"], flag["fallback"], flag["role"]),
                         (self.clock() + STALL_SECONDS, self.clock(), "k3_balanced", "pro_asap", "architect"))
        alerts = self.alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual((alerts[0]["alert"], alerts[0]["window"], alerts[0]["fallback"]), (True, "balanced", "pro_asap"))

    def test_while_flagged_every_call_on_the_window_goes_straight_to_its_fallback(self):
        self.ask()
        self.provider.calls.clear()
        self.clock.advance(600)
        answer = self.ask("pro_balanced", key="review-1", role="review")
        self.assertEqual(self.provider.calls, [("pro_asap", fallback_key("review-1", "pro_asap"))], "no 15-minute wait first")
        self.assertEqual(answer["sail_fallback"]["why"], "flagged")
        self.assertEqual(len(self.alerts()), 1, "one alert a stall")

    def test_after_the_hour_the_window_is_asked_again(self):
        self.ask()
        self.provider.stalled.clear()  # the queue is back
        self.provider.calls.clear()
        self.clock.advance(STALL_SECONDS + 1)
        answer = self.ask(key="arch-2")
        self.assertEqual(self.provider.calls, [("k3_balanced", "arch-2")])
        self.assertEqual(answer["model"], "k3_balanced")
        self.assertEqual(set(answer), {"text", "json", "route", "model", "cost_usd", "fallback_reasons", "truncated",
                                       "incomplete_reason", "usage"}, "an answer with no fallback reads exactly as before")

    def test_a_stall_that_continues_past_the_hour_is_not_alerted_again_a_new_one_is(self):
        self.ask()
        since = self.clock()
        self.clock.advance(STALL_SECONDS + 60)
        self.ask(key="arch-2")
        self.assertEqual(len(self.alerts()), 1, "the same stall, flagged again")
        self.assertEqual(self.store.get(STALL_KEY)["balanced"]["since"], since)
        self.clock.advance(3 * STALL_SECONDS)
        self.ask(key="arch-3")
        self.assertEqual(len(self.alerts()), 2, "a new stall hours after the last flag ended")


class TheAuditKeepsItsModel(Case):
    """The gate's audit (Kimi-K3 on Sail) is a second model, different from the review's DeepSeek-V4-Pro: its fallback is
    Kimi-K3's asap profile, never the map's pro_asap, so a stalled balanced window never makes one model read twice."""

    def test_a_stalled_audit_retries_on_its_own_models_asap_profile(self):
        answer = self.ask("k3_balanced", key="audit-1", role="audit")
        self.assertEqual(self.provider.calls, [("k3_balanced", "audit-1"), ("k3", fallback_key("audit-1", "k3"))])
        self.assertEqual(model_of(answer["model"]), model_of("k3_balanced"))
        self.assertEqual(answer["sail_fallback"], {"from": "k3_balanced", "to": "k3", "why": "stall"})
        self.assertEqual(self.store.get(STALL_KEY)["balanced"]["fallback"], "k3")

    def test_while_flagged_the_audit_goes_to_its_own_models_asap_profile_and_the_review_to_the_map(self):
        self.ask()  # the architect's poll timeout flags the window (to pro_asap)
        self.provider.calls.clear()
        review = self.ask("pro_balanced", key="review-1", role="review")
        audit = self.ask("k3_balanced", key="audit-1", role="audit")
        self.assertEqual([p for p, _ in self.provider.calls], ["pro_asap", "k3"])
        self.assertNotEqual(model_of(review["model"]), model_of(audit["model"]), "two readers, not one model twice")

    def test_the_roles_are_a_setting(self):
        self.settings["sail_fallback_same_model"] = None
        self.assertEqual(self.router.sail_fallback("k3_balanced", role="audit"), ("balanced", "pro_asap"))
        self.settings["sail_fallback_same_model"] = ["audit", "architect"]
        self.assertEqual(self.router.sail_fallback("k3_balanced", role="architect"), ("balanced", "k3"))
        self.assertEqual(self.router.sail_fallback("k3_balanced", role="review"), ("balanced", "pro_asap"))
        del self.settings["sail_fallback_same_model"]
        self.assertEqual(self.router.sail_fallback("k3_balanced", role="audit"), ("balanced", "k3"), "absent: the audit")
        self.settings["sail_fallback"] = None
        self.assertIsNone(self.router.sail_fallback("k3_balanced", role="audit"), "the map off is every fallback off")

    def test_asap_twin(self):
        self.assertEqual((asap_twin("k3_balanced"), asap_twin("pro_balanced"), asap_twin("no_such_profile")),
                         ("k3", "pro_asap", None))


class NoFallback(Case):
    def test_an_asap_profile_or_another_error_or_no_map_is_not_retried(self):
        self.provider.stalled = {"asap"}
        with self.assertRaisesRegex(ModelError, "provider_poll_timeout"):
            self.ask("pro_asap")
        self.assertEqual(len(self.provider.calls), 1)
        self.provider = FakeProvider(error="provider_http_400")
        self.router.provider = self.provider
        with self.assertRaisesRegex(ModelError, "provider_http_400"):
            self.ask()
        self.assertEqual([p for p, _ in self.provider.calls], ["k3_balanced"])
        self.settings["sail_fallback"] = None
        self.provider = self.router.provider = FakeProvider()
        with self.assertRaises(ModelError):
            self.ask()
        self.assertEqual([p for p, _ in self.provider.calls], ["k3_balanced"])
        self.assertIsNone(self.store.get(STALL_KEY), "no map, no flag")
        self.assertEqual(self.alerts(), [])

    def test_a_map_entry_to_a_profile_outside_asap_or_to_null_is_ignored(self):
        self.settings["sail_fallback"] = {"k3_balanced": "flash_balanced", "pro_balanced": None}
        self.assertIsNone(self.router.sail_fallback("k3_balanced"))
        self.assertIsNone(self.router.sail_fallback("pro_balanced"))
        self.assertIsNone(self.router.sail_fallback("no_such_profile"))
        self.settings["sail_fallback"] = {"k3_balanced": "k3"}
        self.assertEqual(self.router.sail_fallback("k3_balanced"), ("balanced", "k3"))

    def test_a_fallback_that_fails_too_is_one_model_error_naming_both(self):
        self.provider.stalled = {"balanced", "asap"}
        with self.assertRaises(ModelError) as caught:
            self.ask()
        self.assertIn("retried on pro_asap", str(caught.exception))
        self.assertEqual([p for p, _ in self.provider.calls], ["k3_balanced", "pro_asap"], "one retry, no more")


if __name__ == "__main__":
    unittest.main()

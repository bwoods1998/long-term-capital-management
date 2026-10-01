"""The architect on Sail (Oct 1, 2026). From 08:15Z every pass on Kimi-K3 at effort "high" spent the whole 32,000-token
output on reasoning and came back `incomplete` (max_output_tokens), most with no text; the router ignored the cut, so each
pass read as no proposals, the salvage never ran, and each empty pass wrote [] over the last real card refusals. Now:
`architect.sail_effort` ("medium" by default) is the pass's effort on Sail and OpenAI (Claude's is its own); the Sail
route says when it was cut (`truncated`, `incomplete_reason`, `usage`); a cut Sail answer's complete families are
salvaged as a Claude one's, its retry on Claude alone; the event says a Sail pass's effort, usage and why it was cut; and a
pass that proposed nothing keeps the last pass's card and structure refusals. Every family and number here is invented."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace

from league.swarm import architect as arch_mod
from league.swarm.architect import (CARD_REFUSALS_KEY, SAIL_EFFORT, SAIL_EFFORTS, STRUCTURE_REFUSALS_KEY, Architect,
                                    sail_usage)
from league.swarm.models import ModelRouter, extract_json
from league.tests.test_claude import message
from league.tests.test_frontier import FakeOpener
from league.tests.test_swarm_cards import proposal as carded
from league.tests.test_swarm_graveyard_digest import RouteCase
from league.tests.test_swarm_rounds import RoundCase

#: The ledger's shape of today's cut passes: the whole output on reasoning.
CUT = {"status": "incomplete", "incomplete_reason": "max_output_tokens", "output_tokens": 32000, "reasoning_tokens": 30500}


def proposal(i, structure="debit_vertical", roots=("SPY",)):
    return {"slug": f"idea-{i}", "mechanism": f"Mechanism number {i}: dealers rebalance and the move reverts within the day.",
            "structure": structure, "roots": list(roots), "dte": [0, 5], "rejection": "no reversion", "sketch": "enter late"}


def families(n, start=0):
    return [proposal(start + i, roots=(("SPY", "QQQ", "IWM")[i % 3],)) for i in range(n)]


def cut_text(n, start=0):
    """An answer cut inside its (n+1)th family: n complete, as Kimi-K3's 10:15Z answer was."""
    text = "```json\n" + json.dumps({"families": families(n + 1, start)}, indent=2)
    return text[: text.rfind('"sketch"')]


class SailCase(RoundCase):
    """The architect on the real router and Provider, Sail its only route (the box: Claude's architect line $0)."""

    def setUp(self):
        super().setUp()
        self.settings["architect"]["openai_model"] = None

    def arch(self) -> Architect:
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def event(self) -> dict:
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.architect"][-1]


class TheRoute(SailCase):
    def ask(self):
        return self.router.ask(role="architect", system="system", user="user", family=None, key="k1", openai_model=None,
                               sail_profile="k3_balanced", max_output=32000, effort="high", need_usd=2.0)

    def test_a_cut_sail_answer_says_so_with_its_reason_and_usage(self):
        text = cut_text(2)
        self.replies = [{"text": text, **CUT}]
        answer = self.ask()
        self.assertIs(answer["truncated"], True)
        self.assertEqual(answer["incomplete_reason"], "max_output_tokens")
        self.assertEqual((answer["usage"]["output_tokens"], answer["usage"]["output_tokens_details"]["reasoning_tokens"]),
                         (32000, 30500))
        # Every other reader sees the answer exactly as before: the same text, the same JSON read from it.
        self.assertEqual(answer["text"], text)
        self.assertEqual(answer["json"], extract_json(text))
        self.assertEqual(set(answer), {"text", "json", "route", "model", "cost_usd", "fallback_reasons", "truncated",
                                       "incomplete_reason", "usage"})

    def test_a_complete_sail_answer_is_not_truncated(self):
        self.replies = [{"text": json.dumps({"families": families(2)})}]
        answer = self.ask()
        self.assertIs(answer["truncated"], False)
        self.assertIsNone(answer["incomplete_reason"])
        self.assertEqual(answer["usage"]["output_tokens"], 800)
        self.assertEqual(len(answer["json"]["families"]), 2)

    def test_an_answer_without_the_providers_fields_is_complete(self):
        # A stand-in Provider (the tests' stubs) gives no `incomplete`: never read as cut.
        router = ModelRouter(self.store, None, settings=self.settings)
        router.sail = lambda *a, **kw: SimpleNamespace(output_text='{"families": []}', cost_usd=Decimal("0.01"))
        answer = router.ask(role="rewrite", system="s", user="u", family="f", key="k", openai_model=None,
                            sail_profile="k3_balanced")
        self.assertEqual((answer["truncated"], answer["incomplete_reason"], answer["usage"]), (False, None, {}))


class TheEffort(SailCase):
    def effort_sent(self) -> str:
        self.replies = [{"text": json.dumps({"families": []})}]
        out = self.arch().run()
        self.clock.advance(4000)
        return self.sail.bodies[-1]["reasoning"]["effort"], out

    def test_sail_is_asked_at_medium_by_default_and_the_event_says_so(self):
        self.assertNotIn("sail_effort", self.settings["architect"], "no settings.py default: the architect's own")
        effort, out = self.effort_sent()
        self.assertEqual(effort, "medium")
        self.assertEqual((out["effort"], self.event()["effort"]), ("medium", "medium"))
        self.assertEqual(SAIL_EFFORT, "medium")

    def test_high_remains_selectable_and_a_typo_reads_as_the_default(self):
        self.settings["architect"]["sail_effort"] = "high"
        self.assertEqual(self.effort_sent()[0], "high")
        for raw in ("hgih", "HIGH", "", None, 3, ["high"]):
            self.settings["architect"]["sail_effort"] = raw
            self.assertEqual(self.effort_sent()[0], "medium", repr(raw))
        for name in SAIL_EFFORTS:
            self.settings["architect"]["sail_effort"] = name
            self.assertEqual(self.arch().sail_effort(), name)

    def test_openai_is_asked_at_the_same_effort(self):
        self.settings["architect"]["openai_model"] = "gpt-6-astra"
        self.month.value = 1000.0
        self.frontier_text = json.dumps({"families": []})
        out = self.arch().run()
        self.assertEqual(out["route"], "openai")
        self.assertEqual(self.asked[-1]["effort"], "medium")
        self.assertEqual(out["effort"], "medium")


class ClaudesEffort(RouteCase):
    def test_claudes_effort_is_its_own(self):
        self.settings["architect"]["sail_effort"] = "low"
        opener = FakeOpener(self.answer(), self.answer())
        out = self.architect(self.router(opener)).run()
        self.assertEqual(out["route"], "claude")
        self.assertEqual(opener.body()["output_config"]["effort"], self.settings["claude"]["effort"])
        self.assertNotIn("effort", out, "a Claude pass's effort is not the Sail setting")
        self.settings["claude"]["role_effort"] = {"architect": "medium"}
        self.clock.advance(4000)
        self.architect(self.router(opener)).run()
        self.assertEqual(opener.body()["output_config"]["effort"], "medium")


class TheSalvage(SailCase):
    def test_the_complete_families_of_a_cut_sail_answer_are_born(self):
        self.replies = [{"text": cut_text(4), **CUT}]
        out = self.arch().run()
        self.assertEqual(out["born"], ["idea-0", "idea-1", "idea-2", "idea-3"])
        self.assertEqual(out["proposed"], 4)
        self.assertEqual(out["truncated"], {"salvaged": 4, "born": 4})
        self.assertEqual(out["incomplete_reason"], "max_output_tokens")
        self.assertEqual(out["usage"], {"input_tokens": 4000, "cached_tokens": 3000, "output_tokens": 32000,
                                        "reasoning_tokens": 30500})
        event = self.event()
        self.assertEqual((event["incomplete_reason"], event["usage"]["reasoning_tokens"], event["route"]),
                         ("max_output_tokens", 30500, "sail"))
        self.assertEqual(len(self.sail.bodies), 1, "four salvaged: no retry, and never a second Sail call")

    def test_a_cut_to_nothing_answer_proposes_nothing_and_its_retry_is_claude_only(self):
        self.replies = [{"text": "", **CUT, "reasoning_tokens": 32000}]
        out = self.arch().run()
        self.assertEqual((out["born"], out["proposed"]), ([], 0))
        self.assertEqual(out["truncated"]["salvaged"], 0)
        retry = out["truncated"]["retry"]
        self.assertEqual(retry["effort"], "medium")
        self.assertIn("no Sail fallback", retry["error"], "Claude has no route here, and the retry never asks Sail")
        self.assertEqual(len(self.sail.bodies), 1)
        self.assertEqual(out["usage"]["reasoning_tokens"], 32000)

    def test_a_complete_sail_pass_has_no_cut(self):
        self.replies = [{"text": json.dumps({"families": families(2)})}]
        out = self.arch().run()
        self.assertEqual(len(out["born"]), 2)
        self.assertFalse({"truncated", "incomplete_reason"} & set(out))
        self.assertEqual(out["usage"]["output_tokens"], 800)


class TheRetryAfterASailCut(RouteCase):
    """Claude first, its architect line $0 (the box): the pass falls to Sail, and a cut there retries on Claude alone."""

    def setUp(self):
        super().setUp()
        self.settings["claude"]["role_usd_day"] = {"architect": 0}

    def sail_router(self, opener, text):
        router = self.router(opener)

        def sail(profile, items, **kw):
            self.sail_calls.append(kw.get("effort"))
            return SimpleNamespace(output_text=text, cost_usd=Decimal("0.34"), incomplete=True,
                                   incomplete_reason="max_output_tokens",
                                   usage={"input_tokens": 13912, "output_tokens": 32000,
                                          "output_tokens_details": {"reasoning_tokens": 25000}})

        router.sail = sail
        return router

    def test_a_retry_the_line_refuses_is_unbilled_and_never_asks_sail_again(self):
        opener = FakeOpener()
        out = self.architect(self.sail_router(opener, cut_text(1))).run()
        self.assertEqual(out["route"], "sail")
        self.assertEqual(out["born"], ["idea-0"])
        self.assertEqual(out["truncated"]["retry"]["kind"], "line")
        self.assertEqual(out["truncated"]["retry"]["billed"], [])
        self.assertEqual((self.sail_calls, opener.calls), (["medium"], []), "one Sail call, nothing dispatched to Claude")

    def test_a_retry_claude_has_room_for_is_born_on_claude(self):
        opener = FakeOpener(self.answer(families(2, start=10)))
        router = self.sail_router(opener, cut_text(1))
        real, seen = router._claude_admit, []

        def admit(**kw):
            seen.append(kw["key"])
            if len(seen) == 1:  # the pass's own call: the line
                kw["errors"].append("claude: the architect line for today has no room")
                return None, "line"
            return real(**kw)

        router._claude_admit = admit
        self.settings["claude"]["role_usd_day"] = {}
        out = self.architect(router).run()
        self.assertEqual(out["born"], ["idea-0", "idea-10", "idea-11"])
        retry = out["truncated"]["retry"]
        self.assertEqual((retry["route"], retry["born"], retry["effort"]), ("claude", 2, "medium"))
        self.assertTrue(seen[1].endswith(":salvage"))
        self.assertEqual(len(self.sail_calls), 1)


class TheRefusalsStay(SailCase):
    OLD_CARDS = {"at": "2026-10-01T07:55:00Z", "items": [{"slug": "old-idea", "why": "incomplete card: falsification"}]}
    OLD_STRUCTURES = {"at": "2026-10-01T07:55:00Z", "rows": [{"slug": "old-condor", "structure": "iron_condor",
                                                              "roots": ["QQQ"]}]}

    def setUp(self):
        super().setUp()
        self.settings["architect"]["require_card"] = True
        self.settings["architect"]["structures"] = ["debit_vertical", "long_butterfly", "long_call", "long_put"]
        self.store.put(CARD_REFUSALS_KEY, self.OLD_CARDS)
        self.store.put(STRUCTURE_REFUSALS_KEY, self.OLD_STRUCTURES)

    def kept(self) -> tuple:
        return self.store.get(CARD_REFUSALS_KEY), self.store.get(STRUCTURE_REFUSALS_KEY)

    def test_an_empty_answer_keeps_the_last_refusals(self):
        for reply in ({"text": json.dumps({"families": []})}, {"text": "{}"}, {"text": "no JSON at all"},
                      {"text": "", **CUT}):
            self.replies = [reply]
            out = self.arch().run()
            self.clock.advance(4000)
            self.assertEqual(out["proposed"], 0, repr(reply))
            self.assertEqual(self.kept(), (self.OLD_CARDS, self.OLD_STRUCTURES), repr(reply))
            self.assertIn("old-idea: incomplete card", self.arch().prompt(), "the next request still shows them")
            self.assertIn("old-condor (iron_condor on QQQ)", self.arch().prompt())

    def test_a_failed_pass_keeps_them(self):
        def boom(*a, **kw):
            raise RuntimeError("provider_http_502")

        self.router.sail = boom
        out = self.arch().run()
        self.assertIn("error", out)
        self.assertEqual(self.kept(), (self.OLD_CARDS, self.OLD_STRUCTURES))

    def test_a_pass_that_proposed_replaces_them(self):
        self.replies = [{"text": json.dumps({"families": [proposal(1), proposal(2, "iron_condor", ("IWM",))]})}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 2)
        cards_now, structures_now = self.kept()
        self.assertEqual([i["slug"] for i in cards_now["items"]], ["idea-1"], "the card it lacked")
        self.assertEqual([r["slug"] for r in structures_now["rows"]], ["idea-2"])
        self.clock.advance(4000)
        self.replies = [{"text": json.dumps({"families": [carded("late-rebound")]})}]
        out = self.arch().run()
        self.assertEqual(out["born"], ["late-rebound"])
        self.assertEqual(self.kept()[0]["items"], [], "a pass that proposed and was refused nothing clears them")
        self.assertEqual(self.kept()[1]["rows"], [])


class TheRetryCountsOnlyItsOwn(RouteCase):
    def test_a_cut_answers_card_refusals_are_counted_once_when_its_retry_never_reaches_admit(self):
        self.settings["architect"]["require_card"] = True
        text = json.dumps({"families": families(2)})
        router = self.router(FakeOpener(message(text[: text.rfind('"sketch"')], stop="max_tokens", cost="0.31")))
        real, seen = router._claude_admit, []

        def admit(**kw):
            seen.append(kw["key"])
            if len(seen) > 1:
                kw["errors"].append("claude: the architect line for today has no room")
                return None, "line"
            return real(**kw)

        router._claude_admit = admit
        out = self.architect(router).run()
        self.assertEqual(out["truncated"]["retry"]["kind"], "line")
        self.assertEqual((out["card_refused"]["incomplete"], len(out["card_refused"]["items"])), (1, 1))
        self.assertEqual([i["slug"] for i in self.store.get(CARD_REFUSALS_KEY)["items"]], ["idea-0"])


class TheUsage(unittest.TestCase):
    def test_sail_usage_keeps_what_the_event_needs(self):
        self.assertEqual(sail_usage({"input_tokens": 13912, "input_tokens_details": {"cached_tokens": 0},
                                     "output_tokens": 10208, "output_tokens_details": {"reasoning_tokens": 3305},
                                     "total_tokens": 24120}),
                         {"input_tokens": 13912, "cached_tokens": 0, "output_tokens": 10208, "reasoning_tokens": 3305})
        self.assertEqual(sail_usage(None), {})
        self.assertEqual(sail_usage({"input_tokens": True, "output_tokens_details": "x"}), {})
        self.assertIn("sail_usage", arch_mod.__all__)

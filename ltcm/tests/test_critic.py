import copy
import unittest
from decimal import Decimal
from types import SimpleNamespace

from ltcm.broker import Instrument, OrderIntent, Position
from ltcm.critic import (
    INSTRUCTIONS,
    LiveOrderCritic,
    build,
    packet,
    parse_verdict,
)
from ltcm.manifest import DeskManifest
from ltcm.risk import Decision
from ltcm.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "alpaca")
DESK = "rosenfeld"
NOW = "2026-09-15T14:30:00.000Z"

RATIONALE = (
    "AAPL beat on services revenue and raised guidance; the drift is not priced in. "
    "Exit on the next print or in ten trading days, whichever comes first."
)


def manifest(**overrides):
    data = copy.deepcopy(SAMPLE)
    data.update(
        {
            "id": DESK,
            "name": "Rosenfeld",
            "venues": ["alpaca"],
            "capital": {"mode": "live", "usd": "1000"},
            "playbook": f"playbooks/{DESK}.md",
        }
    )
    data.update(overrides)
    return DeskManifest.from_dict(data)


def intent(**overrides):
    fields = {
        "desk_id": DESK,
        "instrument": AAPL,
        "side": "buy",
        "quantity": "10",
        "order_type": "limit",
        "limit_price": "189.50",
        "rationale": RATIONALE,
        "created_at": NOW,
        "session_id": "s1",
    }
    fields.update(overrides)
    return OrderIntent.new(**fields)


def decision(order: OrderIntent, **overrides):
    fields = {
        "intent_id": order.id,
        "desk_id": order.desk_id,
        "approved": True,
        "reasons": (),
        "reference_price": Decimal("189.20"),
        "notional": Decimal("1892.00"),
        "checked_at": NOW,
    }
    fields.update(overrides)
    return Decision(**fields)


class FakeProvider:
    """Records every kwarg and replays a scripted answer, or raises one."""

    def __init__(self, text='{"verdict": "approve", "reason": "The order matches the plan."}'):
        self.text = text
        self.raises = None
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        if self.raises is not None:
            raise self.raises
        return SimpleNamespace(output_text=self.text, cost_usd=Decimal("0.001"))


class PacketTests(unittest.TestCase):
    def test_the_packet_carries_everything_the_critic_needs_and_nothing_else(self):
        order = intent()
        body = packet(
            intent=order,
            manifest=manifest(),
            decision=decision(order),
            positions={
                AAPL.key: Position(AAPL, Decimal("30"), Decimal("180"), Decimal("190"), NOW)
            },
            memo="Watching AAPL into the print; sized half until services growth confirms.",
        )
        self.assertIn("Rosenfeld (rosenfeld)", body)
        self.assertIn("Trade post-earnings drift", body)  # the mandate
        self.assertIn("max 25% of desk equity in one position", body)  # the limits
        self.assertIn("equity AAPL on alpaca", body)
        self.assertIn("- side: buy", body)
        self.assertIn("- quantity: 10", body)
        self.assertIn("- order type: limit", body)
        self.assertIn("- limit price: 189.50", body)
        self.assertIn("reference price: 189.20", body)
        self.assertIn("notional: 1892.00 USD", body)
        self.assertIn("services revenue", body)  # the rationale
        self.assertIn("Watching AAPL into the print", body)  # the memo
        self.assertIn("equity:AAPL:alpaca: 30 at average cost 180", body)

    def test_a_market_order_with_no_memo_and_no_book_still_reads_cleanly(self):
        order = intent(order_type="market", limit_price=None)
        body = packet(intent=order, manifest=manifest(), decision=decision(order))
        self.assertIn("- limit price: none (market order)", body)
        self.assertIn("The desk's latest memo:\n(none)", body)
        self.assertIn("Positions the desk holds now:\n- none", body)

    def test_long_text_is_clipped_rather_than_sent_whole(self):
        order = intent(rationale="x" * 2000)
        body = packet(
            intent=order,
            manifest=manifest(),
            decision=decision(order),
            memo="y" * 5000,
        )
        self.assertNotIn("y" * 1600, body)
        self.assertIn("…", body)

    def test_the_instructions_name_the_five_things_the_critic_judges(self):
        for phrase in (
            "side contradicts the rationale",
            "size or the limit price is inconsistent",
            "instrument is one the rationale never mentions",
            "adds to a position the desk already holds",
            "no catalyst and no exit",
            "When in doubt, approve",
        ):
            self.assertIn(phrase, INSTRUCTIONS)
        self.assertIn('{"verdict": "approve"|"block", "reason": "<one sentence>"}', INSTRUCTIONS)


class ParseTests(unittest.TestCase):
    def test_strict_json_is_accepted(self):
        self.assertEqual(
            parse_verdict('{"verdict": "block", "reason": "The rationale argues to sell."}'),
            ("block", "The rationale argues to sell."),
        )

    def test_a_fenced_block_is_unwrapped(self):
        self.assertEqual(
            parse_verdict('```json\n{"verdict": "approve", "reason": "Consistent."}\n```'),
            ("approve", "Consistent."),
        )

    def test_anything_else_is_unusable(self):
        for output in (
            "",
            None,
            "approve",
            "The order looks fine to me.",
            '{"verdict": "maybe", "reason": "unsure"}',
            '{"verdict": "block"}',
            '{"verdict": "block", "reason": "   "}',
            '{"verdict": "block", "reason": 7}',
            '["approve"]',
            '{"verdict": "approve", "reason": "ok"} and one more thing',
        ):
            self.assertIsNone(parse_verdict(output), output)

    def test_a_long_reason_is_clipped_to_one_sentence_worth(self):
        verdict, reason = parse_verdict(
            '{"verdict": "block", "reason": "' + "why " * 200 + '"}'
        )
        self.assertEqual(verdict, "block")
        self.assertLessEqual(len(reason), 300)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.critic = LiveOrderCritic(self.provider)
        self.manifest = manifest()
        self.intent = intent()
        self.decision = decision(self.intent)

    def review(self, **kwargs):
        return self.critic.review(
            intent=self.intent,
            manifest=self.manifest,
            decision=self.decision,
            **kwargs,
        )

    def test_one_cheap_call_on_the_desks_own_budget(self):
        review = self.review()
        self.assertEqual(review.verdict, "approve")
        self.assertEqual(review.reason, "The order matches the plan.")
        self.assertEqual(review.model, "zai-org/GLM-5.3")
        self.assertFalse(review.blocked)

        call = self.provider.calls[0]
        self.assertEqual(call["profile"], "glm_asap")
        self.assertIsNone(call["tools"])
        self.assertEqual(call["reasoning_effort"], "low")
        self.assertEqual(call["max_output_tokens"], 1024)
        self.assertEqual(call["request_key"], f"critic:{self.intent.id}")
        self.assertEqual(call["desk_id"], DESK)
        self.assertEqual(call["session_id"], "s1")
        self.assertEqual(call["desk_cap_usd_per_day"], self.manifest.budget_usd_per_day)
        self.assertEqual(call["items"][0]["content"], INSTRUCTIONS)
        self.assertIn("Rosenfeld", call["items"][1]["content"])

    def test_a_block_comes_back_as_a_block(self):
        self.provider.text = '{"verdict": "block", "reason": "The rationale argues to sell."}'
        review = self.review()
        self.assertTrue(review.blocked)
        self.assertEqual(
            review.payload(self.intent.id, DESK),
            {
                "intent_id": self.intent.id,
                "desk_id": DESK,
                "verdict": "block",
                "reason": "The rationale argues to sell.",
                "model": "zai-org/GLM-5.3",
            },
        )

    def test_a_provider_failure_is_an_error_verdict_not_an_exception(self):
        class Refused(RuntimeError):
            code = "provider_budget_exceeded"

        self.provider.raises = Refused("provider_budget_exceeded")
        review = self.review()
        self.assertEqual(review.verdict, "error")
        self.assertIn("provider_budget_exceeded", review.reason)
        self.assertFalse(review.blocked)

    def test_unparseable_output_is_an_error_verdict(self):
        self.provider.text = "I think this one is fine."
        self.assertEqual(self.review().verdict, "error")

    def test_no_provider_is_an_error_verdict(self):
        self.assertEqual(LiveOrderCritic(None).review(
            intent=self.intent, manifest=self.manifest, decision=self.decision
        ).verdict, "error")

    def test_the_reason_never_carries_a_response_body(self):
        self.provider.raises = ValueError("HTTP 500: {'secret': 'sk-live-123'}")
        review = self.review()
        self.assertNotIn("sk-live", review.reason)
        self.assertIn("ValueError", review.reason)


class BuildTests(unittest.TestCase):
    def test_the_defaults_come_from_the_service_configuration(self):
        critic = build(FakeProvider(), {})
        self.assertEqual(critic.profile, "glm_asap")
        self.assertEqual(critic.reasoning_effort, "low")
        self.assertEqual(critic.max_output_tokens, 1024)

    def test_a_configured_profile_is_used(self):
        critic = build(FakeProvider(), {"critic_profile": "glm_flash_asap"})
        self.assertEqual(critic.profile, "glm_flash_asap")
        self.assertEqual(critic.model(), "zai-org/GLM-5.3-Flash")

    def test_switched_off_or_without_a_provider_there_is_no_critic(self):
        self.assertIsNone(build(FakeProvider(), {"critic_enabled": False}))
        self.assertIsNone(build(None, {}))

    def test_an_unknown_profile_still_names_itself(self):
        critic = build(FakeProvider(), {"critic_profile": "not_a_profile"})
        self.assertEqual(critic.model(), "not_a_profile")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

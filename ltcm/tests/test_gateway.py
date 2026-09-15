import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import (
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    UnknownOutcome,
    VenueUnavailable,
)
from ltcm.critic import CriticReview
from ltcm.events import EventLog
from ltcm.gateway import Gateway, GatewayError
from ltcm.ledger import DeskLedger
from ltcm.manifest import DeskManifest
from ltcm.risk import RiskEngine
from ltcm.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "alpaca")
DESK = "earnings-01"
NOW = "2026-09-14T14:30:00.000Z"


class FakeBroker:
    """A venue that does exactly what the test tells it to, and nothing else."""

    venue = "shadow"

    def __init__(self, *, price="100", instant_fill=True, raises=None, caps=None):
        self.price = Decimal(price)
        self.instant_fill = instant_fill
        self.raises = raises
        self.caps = caps or {"equity", "option", "limit", "shadow", "fractional"}
        self.orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self.venue_positions: list[Position] = []
        self.submitted: list[str] = []
        self.cancelled: list[str] = []

    # -- reads ------------------------------------------------------------
    def capabilities(self):
        return set(self.caps)

    def quote(self, instrument):
        return Quote(instrument, self.price - 1, self.price + 1, self.price, NOW, "fake", False)

    def balance(self):
        from ltcm.broker import Balance

        return Balance("shadow", Decimal("1000"), Decimal("1000"), Decimal("1000"), NOW)

    def positions(self):
        return list(self.venue_positions)

    def open_orders(self):
        return [o for o in self.orders.values() if not o.terminal]

    def get_order(self, order_id):
        return self.orders[order_id]

    def fills(self, since=None):
        return [f for f in self._fills if since is None or f.at > since]

    # -- writes -----------------------------------------------------------
    def submit(self, intent: OrderIntent) -> Order:
        if self.raises is not None:
            raise self.raises
        self.submitted.append(intent.id)
        existing = self.orders.get("ord-" + intent.id[3:])
        if existing is not None:  # the protocol requires idempotency on the intent
            return existing
        order = Order.from_intent(intent, venue=self.venue)
        order.status = "accepted"
        order.broker_order_id = "vx-" + order.id[-6:]
        order.submitted_at = intent.created_at
        self.orders[order.id] = order
        if self.instant_fill:
            self.complete(order.id)
        return self.orders[order.id]

    def complete(self, order_id, *, at=NOW, price=None):
        order = self.orders[order_id]
        price = Decimal(str(price)) if price is not None else self.price
        order.status = "filled"
        order.filled_quantity = order.quantity
        order.average_price = price
        order.updated_at = at
        self._fills.append(
            Fill(
                id=f"fl-{order.id[-6:]}-{len(self._fills)}",
                order_id=order.id,
                desk_id=order.desk_id,
                instrument=order.instrument,
                side=order.side,
                quantity=order.quantity,
                price=price,
                fee=Decimal("0.01"),
                at=at,
            )
        )
        self.venue_positions = self._derive_positions()
        return order

    def cancel(self, order_id):
        order = self.orders[order_id]
        order.status = "cancelled"
        order.reason = "cancelled by desk"
        self.cancelled.append(order_id)
        return order

    def _derive_positions(self):
        by_key: dict[str, Position] = {}
        for fill in self._fills:
            signed = fill.quantity if fill.side == "buy" else -fill.quantity
            held = by_key.get(fill.instrument.key)
            if held is None:
                by_key[fill.instrument.key] = Position(fill.instrument, signed, fill.price)
            else:
                held.quantity += signed
        return [p for p in by_key.values() if p.quantity != 0]


class GatewayCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = EventLog(self.root / "events.sqlite")
        self.manifest = DeskManifest.from_dict(SAMPLE)
        self.ledger = DeskLedger(self.log, DESK)
        self.broker = FakeBroker()
        self.kill = self.root / "KILL"
        self.gateway = Gateway(
            self.log,
            RiskEngine(),
            {"shadow": self.broker},
            {DESK: self.ledger},
            data=None,
            manifests={DESK: self.manifest},
            kill_switch_path=self.kill,
        )
        self.fund("1000")

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def fund(self, amount, at="2026-09-14T12:00:00.000Z"):
        self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {DESK: str(amount)}, "reasons": {}},
            at=at,
        )

    def intent(self, side="buy", quantity="2", order_type="market", limit_price=None, nonce=None):
        return OrderIntent.new(
            desk_id=DESK,
            instrument=AAPL,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            rationale="post-earnings drift on a documented revenue beat",
            created_at=NOW,
            session_id="s1",
            nonce=nonce,
        )

    def kinds(self):
        return [e.kind for e in self.log.read(limit=1000)]


class ApprovalTests(GatewayCase):
    def test_approved_intent_is_submitted_filled_and_recorded(self):
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(result["status"], "filled")
        self.assertEqual(len(result["fills"]), 1)

        by_kind = {}
        for event in self.log.read(limit=1000):
            by_kind.setdefault(event.kind, []).append(event)
        self.assertEqual(len(by_kind["desk.intent"]), 1)
        self.assertEqual(len(by_kind["risk.decision"]), 1)
        self.assertEqual(len(by_kind["broker.fill"]), 1)
        # This venue fills on submission, so the first order event is already the terminal one.
        self.assertEqual([e.payload["status"] for e in by_kind["broker.order"]], ["filled"])
        # Intents and orders are private until the order is terminal; fills are public at once.
        self.assertFalse(by_kind["desk.intent"][0].public)
        self.assertFalse(by_kind["broker.order"][0].public)
        self.assertTrue(by_kind["broker.fill"][0].public)
        self.assertTrue(by_kind["risk.decision"][0].public)

        state = self.ledger.state(NOW)
        self.assertEqual(state.positions[AAPL.key].quantity, Decimal("2"))
        self.assertEqual(state.cash, Decimal("1000") - Decimal("200") - Decimal("0.01"))
        self.assertEqual(state.fees, Decimal("0.01"))

    def test_proposing_the_same_intent_twice_does_not_duplicate_the_order(self):
        first = self.gateway.propose(self.intent(quantity="1"), NOW)
        before = self.log.latest_seq()
        again = self.gateway.propose(self.intent(quantity="1"), NOW)
        self.assertEqual(again["order_id"], first["order_id"])
        self.assertEqual(self.log.latest_seq(), before)  # every id is derived, so nothing repeats
        self.assertEqual(len(self.broker.submitted), 2)  # the venue deduped on the intent id
        self.assertEqual(self.ledger.state(NOW).positions[AAPL.key].quantity, Decimal("1"))

    def test_a_repeat_is_re_checked_against_the_book_it_created(self):
        self.gateway.propose(self.intent(), NOW)
        again = self.gateway.propose(self.intent(), NOW)
        self.assertFalse(again["approved"])
        self.assertEqual(again["reasons"], ["position would be 40% of desk equity, cap 25%"])
        self.assertEqual(len(self.log.read(kind="broker.fill")), 1)

    def test_rejected_intent_never_reaches_the_broker(self):
        result = self.gateway.propose(self.intent(quantity="100"), NOW)
        self.assertFalse(result["approved"])
        self.assertIn("insufficient desk cash: need 10100.00, have 1000.00", result["reasons"])
        self.assertIsNone(result["order"])
        self.assertEqual(self.broker.submitted, [])
        self.assertNotIn("broker.order", self.kinds())
        decision = self.log.read(kind="risk.decision")[0]
        self.assertFalse(decision.payload["approved"])
        self.assertEqual(decision.payload["desk_id"], DESK)

    def test_kill_switch_stops_everything(self):
        self.kill.write_text("engaged")
        result = self.gateway.propose(self.intent(), NOW)
        self.assertFalse(result["approved"])
        self.assertIn("kill switch engaged", result["reasons"])
        self.assertEqual(self.broker.submitted, [])

    def test_risk_context_is_assembled_from_ledger_broker_and_floor(self):
        ctx = self.gateway.risk_context(self.intent(), NOW)
        self.assertEqual(ctx.desk_equity, Decimal("1000"))
        self.assertEqual(ctx.desk_cash, Decimal("1000"))
        # This desk is shadow, and a scored book is never part of the floor's real equity.
        self.assertEqual(ctx.floor_equity, Decimal("0"))
        self.assertEqual(ctx.quote.last, Decimal("100"))
        self.assertEqual(ctx.venue_capabilities, self.broker.capabilities())
        self.assertFalse(ctx.kill_switch)
        self.assertIsNone(ctx.market_open)  # no calendar source configured
        self.assertEqual(ctx.desk_orders_today, 0)

    def test_a_shadow_order_is_routed_to_the_book_and_says_so(self):
        """Same intent, same engine, same decision -- and nothing sent anywhere."""
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertTrue(self.gateway.shadow_desk(DESK))
        self.assertEqual(self.gateway.route(DESK, "alpaca"), "shadow")
        order = self.log.read(kind="broker.order")[-1]
        self.assertEqual(order.stream, "broker:shadow")
        self.assertEqual(order.payload["venue"], "shadow")
        self.assertTrue(order.payload["shadow"])
        # The instrument still names the venue the desk would have traded on.
        self.assertEqual(order.payload["instrument"]["venue"], "alpaca")
        fill = self.log.read(kind="broker.fill")[-1]
        self.assertTrue(fill.payload["shadow"])
        self.assertEqual(fill.payload["venue"], "shadow")

    def test_a_live_order_carries_no_shadow_flag(self):
        self.gateway.manifests[DESK] = DeskManifest.from_dict(
            {**copy.deepcopy(SAMPLE), "capital": {"mode": "live", "usd": "1000"}}
        )
        self.gateway.brokers["alpaca"] = FakeBroker()
        self.gateway.brokers["alpaca"].venue = "alpaca"
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        order = self.log.read(kind="broker.order")[-1]
        self.assertEqual(order.stream, "broker:alpaca")
        self.assertNotIn("shadow", order.payload)
        self.assertNotIn("shadow", self.log.read(kind="broker.fill")[-1].payload)

    def test_orders_today_feeds_the_daily_count(self):
        self.gateway.propose(self.intent(quantity="1", nonce="a"), NOW)
        self.gateway.propose(self.intent(quantity="1", nonce="b"), NOW)
        self.assertEqual(self.gateway.orders_today(DESK, NOW[:10]), 2)
        self.assertEqual(self.gateway.orders_today(DESK, "2026-01-01"), 0)

    def test_venue_rejection_is_terminal_and_public(self):
        self.broker.raises = RejectedOrder("insufficient buying power at the venue")
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"])
        self.assertEqual(result["status"], "rejected")
        order = self.log.read(kind="broker.order")[-1]
        self.assertIn("insufficient buying power", order.payload["reason"])
        self.assertIn(order.id, self.gateway.release_deferred_events())

    def test_venue_unavailable_is_recorded_not_swallowed(self):
        self.broker.raises = VenueUnavailable("connection reset")
        result = self.gateway.propose(self.intent(), NOW)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("venue unavailable", result["order"]["reason"])
        self.assertIn("ops.alert", self.kinds())


class UnknownOutcomeTests(GatewayCase):
    def test_unknown_outcome_blocks_the_desk_until_reconciliation(self):
        self.broker.raises = UnknownOutcome("no response after submit")
        result = self.gateway.propose(self.intent(), NOW)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(self.gateway.blocked_desks, {DESK: result["order_id"]})

        self.broker.raises = None
        blocked = self.gateway.propose(self.intent(nonce="second"), NOW)
        self.assertFalse(blocked["approved"])
        self.assertTrue(blocked["blocked"])
        self.assertIn("reconcile first", blocked["reasons"][0])
        self.assertEqual(self.broker.submitted, [])

        report = self.gateway.reconcile("shadow", NOW)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(self.gateway.blocked_desks, {})
        self.assertFalse(self.gateway.reconciliation_mismatch)

        after = self.gateway.propose(self.intent(nonce="third"), NOW)
        self.assertTrue(after["approved"], after["reasons"])
        self.assertEqual(after["status"], "filled")

    def test_unknown_order_is_never_left_pending_after_reconciliation(self):
        self.broker.raises = UnknownOutcome("timeout")
        result = self.gateway.propose(self.intent(), NOW)
        self.gateway.reconcile("shadow", NOW)
        statuses = [
            e.payload["status"]
            for e in self.log.read(kind="broker.order")
            if e.payload["order_id"] == result["order_id"]
        ]
        self.assertEqual(statuses, ["unknown", "rejected"])
        self.assertIn(result["order_id"], [o["order_id"] for o in self.gateway.orders(DESK)])


class ReconcileTests(GatewayCase):
    def test_clean_reconciliation_counts_matches(self):
        self.gateway.propose(self.intent(), NOW)
        report = self.gateway.reconcile("shadow", NOW)
        self.assertEqual(report["venue"], "shadow")
        self.assertEqual(report["matches"], 1)
        self.assertEqual(report["mismatches"], [])
        event = self.log.read(kind="broker.reconciled")[-1]
        self.assertTrue(event.public)

    def test_mismatch_trips_the_floor_breaker(self):
        self.gateway.propose(self.intent(), NOW)
        self.broker.venue_positions = [Position(AAPL, Decimal("7"), Decimal("100"))]
        report = self.gateway.reconcile("shadow", NOW)
        self.assertEqual(
            report["mismatches"], [{"instrument": AAPL.key, "ledger": "2", "venue": "7"}]
        )
        self.assertTrue(self.gateway.reconciliation_mismatch)
        breaker = self.log.read(kind="risk.breaker")[-1]
        self.assertEqual(breaker.payload["scope"], "floor")
        self.assertEqual(breaker.payload["rule"], "reconciliation")
        self.assertEqual(breaker.payload["action"], "halt_new_orders")

    def test_reconcile_needs_a_configured_venue(self):
        with self.assertRaises(GatewayError):
            self.gateway.reconcile("alpaca", NOW)


class LifecycleTests(GatewayCase):
    def setUp(self):
        super().setUp()
        self.broker.instant_fill = False

    def test_poll_orders_records_a_later_fill(self):
        result = self.gateway.propose(self.intent(), NOW)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(self.ledger.state(NOW).positions, {})
        self.assertEqual(self.gateway.release_deferred_events(), [])

        self.broker.complete(result["order_id"], at="2026-09-14T14:35:00.000Z")
        changed = self.gateway.poll_orders("2026-09-14T14:35:00.000Z")
        self.assertEqual([c["status"] for c in changed], ["filled"])
        self.assertEqual(
            self.ledger.state("2026-09-14T14:35:00.000Z").positions[AAPL.key].quantity,
            Decimal("2"),
        )
        released = self.gateway.release_deferred_events()
        released_kinds = sorted({self.log.get(i).kind for i in released})
        self.assertEqual(released_kinds, ["broker.order", "desk.intent"])
        self.assertEqual(len(released), 3)  # the intent plus both order states

    def test_cancel_is_terminal_and_releases_the_intent(self):
        result = self.gateway.propose(self.intent(), NOW)
        row = self.gateway.cancel(DESK, result["order_id"], "2026-09-14T14:40:00.000Z")
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(self.broker.cancelled, [result["order_id"]])
        released = self.gateway.release_deferred_events()
        intent_event = self.log.read(kind="desk.intent")[0]
        self.assertIn(intent_event.id, released)

    def test_cancel_refuses_another_desk_and_unknown_orders(self):
        result = self.gateway.propose(self.intent(), NOW)
        with self.assertRaises(GatewayError):
            self.gateway.cancel("kalshi-01", result["order_id"])
        with self.assertRaises(GatewayError):
            self.gateway.cancel(DESK, "ord-nope")

    def test_rejected_intents_are_released_without_an_order(self):
        self.gateway.propose(self.intent(quantity="100"), NOW)
        intent_event = self.log.read(kind="desk.intent")[0]
        self.assertFalse(intent_event.public)
        self.assertEqual(self.gateway.release_deferred_events(), [intent_event.id])

    def test_gateway_rebuilds_its_order_book_from_the_log(self):
        result = self.gateway.propose(self.intent(), NOW)
        rebuilt = Gateway(
            self.log,
            RiskEngine(),
            {"shadow": self.broker},
            {DESK: DeskLedger(self.log, DESK)},
            manifests={DESK: self.manifest},
            kill_switch_path=self.kill,
        )
        self.assertEqual([o["order_id"] for o in rebuilt.orders(DESK)], [result["order_id"]])
        self.assertEqual(rebuilt.open_orders(DESK)[0]["status"], "accepted")


# --------------------------------------------------------------------------- the live critic

ALPACA_AAPL = Instrument("equity", "AAPL", "alpaca")


class RecordingCritic:
    """Stands in for `critic.LiveOrderCritic`: replays a verdict and records the packet inputs."""

    def __init__(self, verdict="approve", reason="Consistent with the rationale."):
        self.verdict = verdict
        self.reason = reason
        self.raises = None
        self.calls = []

    def review(self, *, intent, manifest, decision, positions=None, memo=None):
        self.calls.append(
            {
                "intent": intent,
                "manifest": manifest,
                "decision": decision,
                "positions": dict(positions or {}),
                "memo": memo,
            }
        )
        if self.raises is not None:
            raise self.raises
        return CriticReview(self.verdict, self.reason, "zai-org/GLM-5.3")


class LiveCriticCase(unittest.TestCase):
    """A desk on live capital, on a live venue, with the critic in the path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = EventLog(self.root / "events.sqlite")
        data = copy.deepcopy(SAMPLE)
        data["venues"] = ["alpaca"]
        data["capital"] = {"mode": "live", "usd": "1000"}
        self.manifest = DeskManifest.from_dict(data)
        self.ledger = DeskLedger(self.log, DESK)
        self.broker = FakeBroker()
        self.broker.venue = "alpaca"
        self.critic = RecordingCritic()
        self.gateway = Gateway(
            self.log,
            RiskEngine(),
            {"alpaca": self.broker},
            {DESK: self.ledger},
            manifests={DESK: self.manifest},
            kill_switch_path=self.root / "KILL",
            critic=self.critic,
        )
        self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {DESK: "1000"}, "reasons": {}},
            at="2026-09-14T12:00:00.000Z",
        )

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def intent(self, **overrides):
        fields = {
            "desk_id": DESK,
            "instrument": ALPACA_AAPL,
            "side": "buy",
            "quantity": "2",
            "order_type": "market",
            "rationale": "post-earnings drift on a documented revenue beat; exit in ten days",
            "created_at": NOW,
            "session_id": "s1",
        }
        fields.update(overrides)
        return OrderIntent.new(**fields)

    def reviews(self):
        return self.log.read(kind="risk.review")

    def decisions(self):
        return self.log.read(kind="risk.decision")


class CriticApprovalTests(LiveCriticCase):
    def test_an_approved_order_is_sent_and_the_review_is_public(self):
        order = self.intent()
        result = self.gateway.propose(order, NOW)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(result["status"], "filled")
        self.assertEqual(self.broker.submitted, [order.id])

        review = self.reviews()[0]
        self.assertTrue(review.public)
        self.assertEqual(review.stream, "risk")
        self.assertEqual(
            review.payload,
            {
                "intent_id": order.id,
                "desk_id": DESK,
                "verdict": "approve",
                "reason": "Consistent with the rationale.",
                "model": "zai-org/GLM-5.3",
            },
        )
        self.assertEqual(len(self.decisions()), 1)

    def test_every_published_review_matches_the_sites_contract(self):
        for verdict in ("approve", "block"):
            self.critic.verdict = verdict
            self.critic.reason = "x" * 5000  # a model that will not stop talking
            self.gateway.propose(self.intent(quantity="1", nonce=verdict), NOW)
        reviews = self.reviews()
        self.assertEqual(len(reviews), 2)
        for review in reviews:
            self.assertEqual(review.stream, "risk")
            self.assertTrue(review.public)
            self.assertEqual(
                sorted(review.payload), ["desk_id", "intent_id", "model", "reason", "verdict"]
            )
            self.assertIn(review.payload["verdict"], ("approve", "block"))
            self.assertRegex(review.payload["desk_id"], r"^[a-z0-9-]{1,40}$")
            self.assertLessEqual(len(review.payload["reason"]), 2000)
            self.assertLessEqual(len(review.payload["model"]), 80)

    def test_the_critic_reads_the_mandate_the_book_and_the_latest_memo(self):
        self.log.append(
            self.manifest.stream,
            "desk.memo",
            {"session_id": "s0", "title": "Into the print", "text": "Half size until services confirm."},
            at="2026-09-14T13:00:00.000Z",
        )
        self.gateway.propose(self.intent(quantity="1"), NOW)
        self.gateway.propose(self.intent(quantity="1", nonce="second"), NOW)
        self.assertEqual(len(self.critic.calls), 2)
        call = self.critic.calls[-1]
        self.assertEqual(call["manifest"].id, DESK)
        self.assertEqual(call["memo"], "Half size until services confirm.")
        self.assertTrue(call["decision"].approved)
        # The second order is judged against the book the first one created.
        self.assertEqual(call["positions"][ALPACA_AAPL.key].quantity, Decimal("1"))


class CriticBlockTests(LiveCriticCase):
    def test_a_block_stops_the_order_and_is_published_as_a_second_decision(self):
        self.critic.verdict = "block"
        self.critic.reason = "The rationale argues the stock is expensive but the order buys."
        order = self.intent()
        result = self.gateway.propose(order, NOW)

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reasons"],
            ["critic: The rationale argues the stock is expensive but the order buys."],
        )
        self.assertIsNone(result["order"])
        self.assertEqual(self.broker.submitted, [])
        self.assertNotIn("broker.order", [e.kind for e in self.log.read(limit=1000)])

        decisions = self.decisions()
        self.assertEqual([d.payload["approved"] for d in decisions], [True, False])
        self.assertEqual(
            decisions[1].payload["reasons"],
            ["critic: The rationale argues the stock is expensive but the order buys."],
        )
        # The engine's own numbers are carried over so the public sees what was nearly sent.
        self.assertEqual(decisions[1].payload["reference_price"], "101")  # the ask a buy pays
        self.assertEqual(self.reviews()[0].payload["verdict"], "block")
        self.assertEqual(self.ledger.state(NOW).positions, {})

    def test_a_blocked_intent_is_released_because_there_is_nothing_to_front_run(self):
        self.critic.verdict = "block"
        self.critic.reason = "No exit is stated."
        self.gateway.propose(self.intent(), NOW)
        intent_event = self.log.read(kind="desk.intent")[0]
        self.assertFalse(intent_event.public)
        self.assertEqual(self.gateway.release_deferred_events(), [intent_event.id])

    def test_a_rebuilt_gateway_still_knows_the_block_was_the_last_word(self):
        self.critic.verdict = "block"
        self.gateway.propose(self.intent(), NOW)
        rebuilt = Gateway(
            self.log,
            RiskEngine(),
            {"alpaca": self.broker},
            {DESK: DeskLedger(self.log, DESK)},
            manifests={DESK: self.manifest},
        )
        intent_event = self.log.read(kind="desk.intent")[0]
        self.assertEqual(rebuilt.release_deferred_events(), [intent_event.id])


class CriticFailureTests(LiveCriticCase):
    def test_a_critic_that_cannot_answer_lets_the_order_through_with_an_alert(self):
        self.critic.verdict = "error"
        self.critic.reason = "critic call failed: provider_timeout"
        order = self.intent()
        result = self.gateway.propose(order, NOW)

        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(self.broker.submitted, [order.id])
        # The site's `risk.review` contract admits approve and block only, so an unanswered
        # review is an alert and nothing on the tape.
        self.assertEqual(self.reviews(), [])
        alert = self.log.last("ops", "ops.alert")
        self.assertEqual(alert.payload["level"], "warning")
        self.assertIn("proceeds on the deterministic engine", alert.payload["text"])
        self.assertEqual(len(self.decisions()), 1)

    def test_a_critic_that_raises_is_not_a_halt(self):
        self.critic.raises = RuntimeError("boom")
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(self.reviews(), [])
        self.assertIn("critic failed", self.log.last("ops", "ops.alert").payload["text"])

    def test_the_engine_still_rejects_before_the_critic_is_ever_asked(self):
        result = self.gateway.propose(self.intent(quantity="100"), NOW)
        self.assertFalse(result["approved"])
        self.assertEqual(self.critic.calls, [])
        self.assertEqual(self.reviews(), [])

    def test_the_real_critic_blocks_end_to_end(self):
        from ltcm.critic import LiveOrderCritic
        from ltcm.tests.test_critic import FakeProvider

        provider = FakeProvider('{"verdict": "block", "reason": "AAPL is never named."}')
        self.gateway.critic = LiveOrderCritic(provider)
        order = self.intent()
        result = self.gateway.propose(order, NOW)
        self.assertFalse(result["approved"])
        self.assertEqual(result["reasons"], ["critic: AAPL is never named."])
        self.assertEqual(self.broker.submitted, [])
        self.assertEqual(provider.calls[0]["request_key"], f"critic:{order.id}")


def live_broker(venue="alpaca"):
    broker = FakeBroker()
    broker.venue = venue
    return broker


class CriticScopeTests(unittest.TestCase):
    """Who the critic is asked about, and who it is not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = EventLog(self.root / "events.sqlite")
        self.manifest = DeskManifest.from_dict(SAMPLE)  # shadow
        self.critic = RecordingCritic()
        self.gateway = Gateway(
            self.log,
            RiskEngine(),
            {"shadow": FakeBroker(), "alpaca": live_broker()},
            {DESK: DeskLedger(self.log, DESK)},
            manifests={DESK: self.manifest},
            critic=self.critic,
        )
        self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {DESK: "1000"}, "reasons": {}},
            at="2026-09-14T12:00:00.000Z",
        )

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def intent(self):
        return OrderIntent.new(
            desk_id=DESK,
            instrument=AAPL,
            side="buy",
            quantity="2",
            rationale="shadow money, real rules",
            created_at=NOW,
            session_id="s1",
        )

    def test_a_shadow_desk_never_pays_for_a_critic(self):
        result = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(self.critic.calls, [])
        self.assertEqual(self.log.read(kind="risk.review"), [])
        self.assertFalse(self.gateway.live_desk(DESK))

    def test_a_promoted_desk_is_live_even_though_its_manifest_says_shadow(self):
        self.log.append(
            "evolution",
            "evolution.promoted",
            {"desk_id": DESK, "family": "earnings", "from": "shadow", "to": "live", "score": {}},
            at="2026-09-14T13:00:00.000Z",
        )
        self.assertTrue(self.gateway.live_desk(DESK))
        self.gateway.propose(self.intent(), NOW)
        self.assertEqual(len(self.critic.calls), 1)

    def test_an_unknown_desk_is_not_live(self):
        self.assertFalse(self.gateway.live_desk("nobody"))

    def test_no_critic_configured_is_simply_no_review(self):
        self.gateway.critic = None
        self.gateway.propose(self.intent(), NOW)
        self.assertEqual(self.log.read(kind="risk.review"), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


KALSHI_TICKER = "KXCPI-26SEP-T3.0"
CPI_YES = Instrument("event", "CPI", "kalshi", market_id=KALSHI_TICKER, right="yes")
CPI_NO = Instrument("event", "CPI", "kalshi", market_id=KALSHI_TICKER, right="no")
SETTLED_AT = "2026-09-15T18:00:00Z"


class SettlingBroker(FakeBroker):
    """A venue that settles markets: it reports settlements and flattens its own positions."""

    venue = "kalshi"

    def __init__(self, rows=(), positions=(), **kwargs):
        super().__init__(**kwargs)
        self.rows = list(rows)
        self.venue_positions = list(positions)
        self.settlement_calls = []
        self.settled_markets = []

    def settlements(self, since=None):
        self.settlement_calls.append(since)
        return [r for r in self.rows if since is None or r["settled_time"] > since]

    def settle_event(self, market_id, payout_per_contract, *, now=None):
        self.settled_markets.append((market_id, str(payout_per_contract), now))
        return []


class SettlementCase(GatewayCase):
    """Settlement is a venue fact, so the desk under test trades that venue for real."""

    def setUp(self):
        super().setUp()
        data = copy.deepcopy(SAMPLE)
        data["venues"] = ["kalshi"]
        data["instruments"] = {**data["instruments"], "asset_classes": ["event"]}
        data["capital"] = {"mode": "live", "usd": "1000"}
        self.manifest = DeskManifest.from_dict(data)
        self.gateway.manifests[DESK] = self.manifest
        self.kalshi = SettlingBroker()
        self.gateway.brokers["kalshi"] = self.kalshi

    def hold(self, instrument, quantity="10", price="0.40", at="2026-09-14T15:00:00.000Z",
             desk_id=DESK):
        """Give the desk a position the honest way: a fill the ledger folds."""
        tag = "fl-open-" + desk_id + "-" + (instrument.right or "yes")
        self.log.append(
            "broker:kalshi",
            "broker.fill",
            {
                "id": tag,
                "fill_id": tag,
                "order_id": "ord-open",
                "desk_id": desk_id,
                "instrument": instrument.to_dict(),
                "side": "buy",
                "quantity": quantity,
                "price": price,
                "fee": "0.17",
                "at": at,
                "venue": "kalshi",
            },
            id="fill:kalshi:" + tag,
            at=at,
        )

    def row(self, result="yes", ticker=KALSHI_TICKER, settled=SETTLED_AT):
        return {
            "ticker": ticker,
            "result": result,
            "yes_count": Decimal("10"),
            "no_count": Decimal("0"),
            "revenue": Decimal("10"),
            "settled_time": settled,
        }

    def outcomes(self):
        return [e.payload for e in self.log.read(kind="desk.outcome", limit=100)]

    def fills(self):
        return [e for e in self.log.read(kind="broker.fill", limit=100)]


class PollSettlementsTests(SettlementCase):
    def test_a_winning_yes_position_is_closed_at_a_dollar_and_scored(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        written = self.gateway.poll_settlements("kalshi")

        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["price"], "1")
        self.assertEqual(written[0]["side"], "sell")
        self.assertEqual(written[0]["fee"], "0")
        self.assertTrue(written[0]["settlement"])
        self.assertEqual(self.ledger.state("2026-09-16T00:00:00.000Z").positions, {})

        outcome = self.outcomes()[0]
        self.assertEqual(outcome["market_id"], KALSHI_TICKER)
        self.assertEqual(outcome["result"], "yes")
        self.assertEqual(outcome["entry_price"], "0.40")
        self.assertEqual(outcome["exit_price"], "1")
        self.assertEqual(outcome["quantity"], "10")
        self.assertEqual(outcome["pnl"], "6.00")
        self.assertEqual(outcome["held_for_hours"], "27.0")

    def test_a_winning_no_position_is_closed_at_a_dollar(self):
        self.hold(CPI_NO, price="0.60")
        self.kalshi.rows = [self.row("no")]
        written = self.gateway.poll_settlements("kalshi")
        self.assertEqual(written[0]["price"], "1")
        self.assertEqual(self.outcomes()[0]["pnl"], "4.00")

    def test_a_losing_no_position_is_closed_at_nothing(self):
        self.hold(CPI_NO, price="0.60")
        self.kalshi.rows = [self.row("yes")]
        written = self.gateway.poll_settlements("kalshi")
        self.assertEqual(written[0]["price"], "0")
        self.assertEqual(self.outcomes()[0]["exit_price"], "0")
        self.assertEqual(self.outcomes()[0]["pnl"], "-6.00")

    def test_the_fill_is_timed_at_the_venues_settled_time_with_the_runbook_id(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        self.gateway.poll_settlements("kalshi")
        event = [e for e in self.fills() if e.payload.get("settlement")][0]
        self.assertEqual(
            event.id, f"fill:kalshi:settlement:{KALSHI_TICKER}:2026-09-15T18:00:00.000Z"
        )
        self.assertEqual(event.at, "2026-09-15T18:00:00.000Z")
        self.assertTrue(event.public)

    def test_polling_twice_writes_nothing_twice(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        self.assertEqual(len(self.gateway.poll_settlements("kalshi")), 1)
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        self.assertEqual(len(self.outcomes()), 1)
        self.assertEqual(len([e for e in self.fills() if e.payload.get("settlement")]), 1)

    def test_a_market_the_desk_never_held_is_ignored(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes", ticker="KXSOMETHINGELSE")]
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        self.assertEqual(self.outcomes(), [])

    def test_a_settlement_with_no_winning_leg_is_alerted_and_skipped(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("")]
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        alerts = [e.payload["text"] for e in self.log.read(kind="ops.alert", limit=50)]
        self.assertTrue(any("no yes/no result" in text for text in alerts), alerts)

    def test_a_position_the_venue_still_shows_open_is_deferred_not_closed(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        self.kalshi.venue_positions = [Position(CPI_YES, Decimal("10"), Decimal("0.40"))]
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        self.assertEqual(self.outcomes(), [])
        # The cursor did not move, so the next poll sees the same settlement again.
        self.kalshi.venue_positions = []
        self.assertEqual(len(self.gateway.poll_settlements("kalshi")), 1)

    def test_a_venue_whose_positions_cannot_be_read_closes_nothing(self):
        class Blind(SettlingBroker):
            def positions(self):
                raise RuntimeError("kalshi is down")

        self.gateway.brokers["kalshi"] = Blind(rows=[self.row("yes")])
        self.hold(CPI_YES)
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        self.assertEqual(self.outcomes(), [])

    def test_a_venue_that_reports_no_settlements_is_a_no_op(self):
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])
        self.assertEqual(self.gateway.poll_settlements("shadow"), [])
        self.assertEqual(self.gateway.poll_settlements("nowhere"), [])

    def test_a_settlements_call_that_raises_is_swallowed(self):
        class Broken(SettlingBroker):
            def settlements(self, since=None):
                raise RuntimeError("boom")

        self.gateway.brokers["kalshi"] = Broken()
        self.hold(CPI_YES)
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])

    def test_the_cursor_advances_so_old_settlements_are_not_re_read(self):
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        self.gateway.poll_settlements("kalshi")
        self.gateway.poll_settlements("kalshi")
        self.assertEqual(self.kalshi.settlement_calls, [None, "2026-09-15T18:00:00.000Z"])

    def test_the_outcome_carries_the_desks_own_rationale(self):
        self.log.append(
            "desk:" + DESK,
            "desk.intent",
            {
                "intent_id": "oi-x",
                "desk_id": DESK,
                "instrument": CPI_YES.to_dict(),
                "side": "buy",
                "quantity": "10",
                "order_type": "limit",
                "limit_price": "0.40",
                "time_in_force": "gtc",
                "rationale": "base rate says 62%, the market says 40%, buying the yes leg",
                "session_id": "s1",
                "created_at": "2026-09-14T15:00:00.000Z",
            },
            id="intent:oi-x",
            at="2026-09-14T15:00:00.000Z",
        )
        self.hold(CPI_YES)
        self.kalshi.rows = [self.row("yes")]
        self.gateway.poll_settlements("kalshi")
        self.assertIn("base rate says 62%", self.outcomes()[0]["rationale_excerpt"])

    def test_a_shadow_position_is_mirrored_into_the_shadow_book(self):
        """A shadow desk's event contract settles too: the score has to know how it came out."""
        book = SettlingBroker()
        book.venue = "shadow"
        self.gateway.brokers["shadow"] = book
        shadow_desk = "earnings-02"
        data = copy.deepcopy(SAMPLE)
        data["id"] = shadow_desk
        data["venues"] = ["kalshi"]
        data["instruments"] = {**data["instruments"], "asset_classes": ["event"]}
        data["playbook"] = f"playbooks/{shadow_desk}.md"
        self.gateway.manifests[shadow_desk] = DeskManifest.from_dict(data)
        self.gateway.ledgers[shadow_desk] = DeskLedger(self.log, shadow_desk)
        self.hold(CPI_NO, desk_id=shadow_desk)
        self.kalshi.rows = [self.row("yes")]
        self.gateway.poll_settlements("kalshi")
        self.assertTrue(self.gateway.shadow_desk(shadow_desk))
        # The yes payout is what the book is told; it pays the NO leg its complement.
        self.assertEqual(book.settled_markets, [(KALSHI_TICKER, "1", "2026-09-15T18:00:00.000Z")])


class BothLegsSettlementTests(SettlementCase):
    """A desk can be long both legs of one market; settling must score each exactly once."""

    def test_both_legs_of_one_market_close_without_colliding(self):
        self.hold(CPI_YES, price="0.40")
        self.hold(CPI_NO, price="0.55")
        self.kalshi.rows = [self.row("yes")]
        written = self.gateway.poll_settlements("kalshi")

        self.assertEqual(len(written), 2)
        self.assertEqual(len({row["fill_id"] for row in written}), 2)
        self.assertEqual(sorted(row["price"] for row in written), ["0", "1"])
        outcomes = self.outcomes()
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(len({o["instrument"] for o in outcomes}), 2)
        # Ten of each leg cost $9.50 and paid $10.00, whichever way the market went.
        self.assertEqual(
            sum(Decimal(o["pnl"]) for o in outcomes), Decimal("0.50")
        )
        self.assertEqual(self.ledger.state("2026-09-16T00:00:00.000Z").positions, {})
        self.assertEqual(self.gateway.poll_settlements("kalshi"), [])

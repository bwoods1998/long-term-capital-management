import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from woodscapital.broker import (
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
from woodscapital.events import EventLog
from woodscapital.gateway import Gateway, GatewayError
from woodscapital.ledger import DeskLedger
from woodscapital.manifest import DeskManifest
from woodscapital.risk import RiskEngine
from woodscapital.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "paper")
DESK = "earnings-01"
NOW = "2026-09-14T14:30:00.000Z"


class FakeBroker:
    """A venue that does exactly what the test tells it to, and nothing else."""

    venue = "paper"

    def __init__(self, *, price="100", instant_fill=True, raises=None, caps=None):
        self.price = Decimal(price)
        self.instant_fill = instant_fill
        self.raises = raises
        self.caps = caps or {"equity", "option", "limit", "paper", "fractional"}
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
        from woodscapital.broker import Balance

        return Balance("paper", Decimal("1000"), Decimal("1000"), Decimal("1000"), NOW)

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
            {"paper": self.broker},
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
        self.assertEqual(ctx.floor_equity, Decimal("1000"))
        self.assertEqual(ctx.quote.last, Decimal("100"))
        self.assertEqual(ctx.venue_capabilities, self.broker.capabilities())
        self.assertFalse(ctx.kill_switch)
        self.assertIsNone(ctx.market_open)  # no calendar source configured
        self.assertEqual(ctx.desk_orders_today, 0)

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

        report = self.gateway.reconcile("paper", NOW)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(self.gateway.blocked_desks, {})
        self.assertFalse(self.gateway.reconciliation_mismatch)

        after = self.gateway.propose(self.intent(nonce="third"), NOW)
        self.assertTrue(after["approved"], after["reasons"])
        self.assertEqual(after["status"], "filled")

    def test_unknown_order_is_never_left_pending_after_reconciliation(self):
        self.broker.raises = UnknownOutcome("timeout")
        result = self.gateway.propose(self.intent(), NOW)
        self.gateway.reconcile("paper", NOW)
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
        report = self.gateway.reconcile("paper", NOW)
        self.assertEqual(report["venue"], "paper")
        self.assertEqual(report["matches"], 1)
        self.assertEqual(report["mismatches"], [])
        event = self.log.read(kind="broker.reconciled")[-1]
        self.assertTrue(event.public)

    def test_mismatch_trips_the_floor_breaker(self):
        self.gateway.propose(self.intent(), NOW)
        self.broker.venue_positions = [Position(AAPL, Decimal("7"), Decimal("100"))]
        report = self.gateway.reconcile("paper", NOW)
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
            {"paper": self.broker},
            {DESK: DeskLedger(self.log, DESK)},
            manifests={DESK: self.manifest},
            kill_switch_path=self.kill,
        )
        self.assertEqual([o["order_id"] for o in rebuilt.orders(DESK)], [result["order_id"]])
        self.assertEqual(rebuilt.open_orders(DESK)[0]["status"], "accepted")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

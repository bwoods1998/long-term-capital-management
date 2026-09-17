import copy
import tempfile
import threading
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

    def test_event_positions_reconcile_on_the_yes_scale(self):
        # The venue reports one signed YES quantity per market (long 20 NO is -20); the ledger
        # holds a leg. Compared by instrument key the two never met, and on Sept 16, 2026 seven
        # live positions no ledger held still read as reconciled.
        market = Instrument("event", "KXHIGHNY-26SEP16-B77.5", "shadow", market_id="KXHIGHNY-26SEP16-B77.5")
        no_leg = Instrument("event", "KXHIGHNY-26SEP16-B77.5", "shadow", market_id="KXHIGHNY-26SEP16-B77.5", right="no")
        self.log.append("broker:shadow", "broker.fill", {
            "fill_id": "f-no", "order_id": "ord-no", "desk_id": DESK, "instrument": no_leg.to_dict(),
            "side": "buy", "quantity": "20", "price": "0.52", "fee": "0", "shadow": True,
        }, id="fill:shadow:f-no", at=NOW)
        self.broker.venue_positions = [Position(market, Decimal("-20"), Decimal("0.52"))]
        report = self.gateway.reconcile("shadow", NOW)
        self.assertEqual(report["mismatches"], [], report)
        self.assertEqual(report["matches"], 1)
        # A venue that holds 25 against the ledger's 20 is a mismatch on that market.
        self.broker.venue_positions = [Position(market, Decimal("-25"), Decimal("0.52"))]
        report = self.gateway.reconcile("shadow", "2026-09-14T14:31:00.000Z")
        self.assertEqual([m["instrument"] for m in report["mismatches"]], ["event:KXHIGHNY-26SEP16-B77.5:shadow"])

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

    def test_a_swept_fill_naming_the_venues_order_id_reaches_the_desks_ledger(self):
        # Kalshi's fills carry Kalshi's order id and no desk. On Sept 16, 2026 seven live
        # positions the venue held sat in no ledger for want of this map.
        result = self.gateway.propose(self.intent(), NOW)
        order = self.broker.orders[result["order_id"]]
        order.broker_order_id = "01a0a89a-venue"
        self.gateway._record_order(order, status="accepted", at=NOW)
        self.assertEqual(self.gateway._venue_orders["01a0a89a-venue"], result["order_id"])
        swept = Fill(id="f-swept", order_id="01a0a89a-venue", desk_id="", instrument=AAPL, side="buy",
                     quantity=Decimal("2"), price=Decimal("101"), fee=Decimal("0.10"), at="2026-09-14T14:36:00.000Z")
        self.broker._fills.append(swept)
        written = self.gateway.ingest_fills(self.broker.venue)
        self.assertEqual(len(written), 1)
        self.assertEqual((written[0]["desk_id"], written[0]["order_id"], written[0]["venue_order_id"]), (DESK, result["order_id"], "01a0a89a-venue"))
        self.assertEqual(self.ledger.state("2026-09-14T14:37:00.000Z").positions[AAPL.key].quantity, Decimal("2"))
        # A fill for an order the floor never placed is recorded as it came, and said once.
        stray = Fill(id="f-stray", order_id="nobody", desk_id="", instrument=AAPL, side="buy",
                     quantity=Decimal("1"), price=Decimal("101"), fee=Decimal("0"), at="2026-09-14T14:38:00.000Z")
        self.broker._fills.append(stray)
        written = self.gateway.ingest_fills(self.broker.venue)
        self.assertEqual(written[0].get("desk_id"), "")
        self.assertTrue(any("did not place" in e.payload.get("text", "") for e in self.log.read(kind="ops.alert")))

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



class SpotOutcomeTests(GatewayCase):
    """A crypto position leaves the ledger by a sell; that sell is where it is scored."""

    BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")

    def fill(self, side, quantity, price, at, tag):
        return Fill(
            id=tag, order_id="ord-" + tag, desk_id=DESK, instrument=self.BTC, side=side,
            quantity=Decimal(quantity), price=Decimal(price), fee=Decimal("0.10"), at=at,
        )

    def outcomes(self):
        return [e.payload for e in self.log.read(kind="desk.outcome", limit=100)]

    def test_a_reducing_sell_writes_an_outcome_at_the_ledgers_average_cost(self):
        self.broker._fills = [
            self.fill("buy", "0.010", "60000", "2026-09-14T13:00:00.000Z", "f1"),
            self.fill("buy", "0.010", "62000", "2026-09-14T13:30:00.000Z", "f2"),
        ]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.outcomes(), [], "buys open; nothing to score yet")
        self.broker._fills.append(self.fill("sell", "0.015", "63000", "2026-09-15T13:00:00.000Z", "f3"))
        self.gateway.ingest_fills("shadow")
        outcomes = self.outcomes()
        self.assertEqual(len(outcomes), 1)
        out = outcomes[0]
        self.assertEqual(out["market_id"], "BTC-USD")
        self.assertEqual(out["result"], "sold")
        self.assertEqual(Decimal(out["entry_price"]), Decimal("61000"))
        self.assertEqual(Decimal(out["exit_price"]), Decimal("63000"))
        self.assertEqual(Decimal(out["quantity"]), Decimal("0.015"))
        self.assertEqual(Decimal(out["pnl"]), Decimal("2000") * Decimal("0.015") - Decimal("0.10"))
        self.assertEqual(out["held_for_hours"], "24.0")
        # Idempotent on the fill: polling again scores nothing twice.
        self.gateway.ingest_fills("shadow")
        self.assertEqual(len(self.outcomes()), 1)

    def test_a_sell_with_nothing_held_scores_nothing(self):
        self.broker._fills = [self.fill("sell", "0.010", "63000", "2026-09-15T13:00:00.000Z", "f9")]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.outcomes(), [])

    def test_a_refused_intent_never_lends_its_sentence(self):
        for intent_id, said, approved in (("oi-ok", "momentum after the halving, out in a day", True), ("oi-no", "YOLO", False)):
            self.log.append(
                "desk:" + DESK, "desk.intent",
                {"intent_id": intent_id, "desk_id": DESK, "instrument": self.BTC.to_dict(), "side": "buy", "quantity": "0.01",
                 "order_type": "limit", "limit_price": "60000", "time_in_force": "gtc", "rationale": said, "session_id": "s1",
                 "created_at": "2026-09-14T12:30:00.000Z"},
                id="intent:" + intent_id, at="2026-09-14T12:30:00.000Z",
            )
            self.log.append(
                "risk", "risk.decision", {"intent_id": intent_id, "desk_id": DESK, "approved": approved, "reasons": []},
                id="decision:" + intent_id, at="2026-09-14T12:31:00.000Z",
            )
        self.broker._fills = [
            self.fill("buy", "0.010", "60000", "2026-09-14T13:00:00.000Z", "g1"),
            self.fill("sell", "0.010", "61000", "2026-09-14T15:00:00.000Z", "g2"),
        ]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.outcomes()[0]["rationale_excerpt"], "momentum after the halving, out in a day")

    def record_intent(self, intent_id, said, at, side="buy", purpose="entry", exit_of=None):
        self.log.append(
            "desk:" + DESK, "desk.intent",
            {"intent_id": intent_id, "desk_id": DESK, "instrument": self.BTC.to_dict(), "side": side, "quantity": "0.01",
             "order_type": "market", "limit_price": None, "time_in_force": "ioc", "rationale": said, "session_id": None,
             "created_at": at, "purpose": purpose, "exit_of": exit_of},
            id="intent:" + intent_id, at=at,
        )

    def test_an_exit_engines_sell_keeps_the_sentence_that_opened_the_position(self):
        # The exit's own intent is newer, and until Sept 16, 2026 it lent the outcome its "Floor
        # exit of ..." sentence, so every stopped-out strategy position read as discretionary.
        self.record_intent("oi-open", "[strategy momo] breakout above the range", "2026-09-14T12:30:00.000Z")
        self.record_intent("oi-exit", "Floor exit of oi-open: the mark reached the stop at 59000.", "2026-09-14T14:59:00.000Z",
                           side="sell", purpose="exit", exit_of="oi-open")
        self.broker._fills = [
            self.fill("buy", "0.010", "60000", "2026-09-14T13:00:00.000Z", "x1"),
            self.fill("sell", "0.010", "59000", "2026-09-14T15:00:00.000Z", "x2"),
        ]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.outcomes()[0]["rationale_excerpt"], "[strategy momo] breakout above the range")
        # A desk's own closing sell is not the entry either.
        self.record_intent("oi-open-2", "[strategy momo] second breakout", "2026-09-14T15:30:00.000Z")
        self.record_intent("oi-sell-2", "taking it off into the close", "2026-09-14T16:59:00.000Z", side="sell")
        self.broker._fills += [
            self.fill("buy", "0.010", "60000", "2026-09-14T16:00:00.000Z", "x3"),
            self.fill("sell", "0.010", "61000", "2026-09-14T17:00:00.000Z", "x4"),
        ]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.outcomes()[1]["rationale_excerpt"], "[strategy momo] second breakout")

    def test_a_second_round_trip_is_held_from_its_own_open(self):
        self.broker._fills = [
            self.fill("buy", "0.010", "60000", "2026-09-10T13:00:00.000Z", "r1"),
            self.fill("sell", "0.010", "60500", "2026-09-10T14:00:00.000Z", "r2"),
            self.fill("buy", "0.010", "60000", "2026-09-14T13:00:00.000Z", "r3"),
            self.fill("sell", "0.010", "60500", "2026-09-14T14:00:00.000Z", "r4"),
        ]
        self.gateway.ingest_fills("shadow")
        outcomes = self.outcomes()
        self.assertEqual([o["held_for_hours"] for o in outcomes], ["1.0", "1.0"])
        self.assertEqual([o["opened_at"] for o in outcomes], ["2026-09-10T13:00:00.000Z", "2026-09-14T13:00:00.000Z"])
        self.assertEqual(self.gateway.entry_of(DESK, self.BTC.key)[0], "2026-09-14T13:00:00.000Z")

    def test_partial_sells_of_one_position_share_its_open_and_its_entry_fees(self):
        self.broker._fills = [
            self.fill("buy", "0.020", "60000", "2026-09-14T13:00:00.000Z", "p1"),
            self.fill("buy", "0.010", "60300", "2026-09-14T13:30:00.000Z", "p2"),
        ]
        self.gateway.ingest_fills("shadow")
        self.broker._fills += [self.fill("sell", "0.010", "59000", f"2026-09-14T15:00:0{k}.000Z", f"p{k + 3}") for k in range(3)]
        self.gateway.ingest_fills("shadow")
        outcomes = self.outcomes()
        self.assertEqual(len(outcomes), 3)
        self.assertEqual({o["opened_at"] for o in outcomes}, {"2026-09-14T13:00:00.000Z"})
        # Two opening fills paid 0.20; each third of the position carries a third of it.
        self.assertEqual([o["entry_fees"] for o in outcomes], ["0.06666667", "0.06666667", "0.06666667"])
        self.assertEqual(Decimal(outcomes[0]["pnl"]), (Decimal("59000") - Decimal("60100")) * Decimal("0.010") - Decimal("0.10"))


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


class EventScoringTests(SettlementCase):
    """An event leg leaves a ledger by settlement or by a sell; both are scored, net of what the
    entry paid."""

    def test_a_settlement_carries_the_entry_fees_and_the_open(self):
        self.hold(CPI_YES, quantity="10", price="0.05")  # the helper's fill pays 0.17
        self.kalshi.rows = [self.row("yes")]
        self.gateway.poll_settlements("kalshi")
        outcome = self.outcomes()[0]
        self.assertEqual((outcome["pnl"], outcome["entry_fees"]), ("9.50", "0.17"))
        self.assertEqual(outcome["opened_at"], "2026-09-14T15:00:00.000Z")

    def test_a_leg_sold_before_its_market_settles_is_scored(self):
        def fill(side, price, at, tag):
            return Fill(id=tag, order_id="o" + tag, desk_id=DESK, instrument=CPI_YES, side=side,
                        quantity=Decimal("10"), price=Decimal(price), fee=Decimal("0.02"), at=at)

        self.broker._fills = [fill("buy", "0.40", "2026-09-14T13:00:00.000Z", "e1"), fill("sell", "0.15", "2026-09-14T15:00:00.000Z", "e2")]
        self.gateway.ingest_fills("shadow")
        self.assertEqual(self.ledger.state("2026-09-14T16:00:00.000Z").positions, {})
        outcomes = self.outcomes()
        self.assertEqual(len(outcomes), 1)
        out = outcomes[0]
        self.assertEqual((out["result"], out["market_id"], out["instrument"]), ("sold", KALSHI_TICKER, CPI_YES.key))
        self.assertEqual(Decimal(out["pnl"]), Decimal("-2.52"))
        self.assertEqual((out["entry_fees"], out["held_for_hours"]), ("0.02", "2.0"))
        # Nothing left to settle, so the settlement scores nothing twice.
        self.kalshi.rows = [self.row("no")]
        self.gateway.poll_settlements("kalshi")
        self.assertEqual(len(self.outcomes()), 1)


class PolledOrderKeepsItsDeskTests(unittest.TestCase):
    def test_an_empty_desk_or_intent_on_a_later_order_event_never_erases_the_known_one(self):
        from ltcm.gateway import Gateway

        class Row:
            def __init__(self, payload, seq):
                self.payload, self.seq, self.kind, self.id, self.public = payload, seq, "broker.order", f"e{seq}", False

        gateway = Gateway.__new__(Gateway)
        gateway._orders, gateway._intent_orders, gateway._venue_orders, gateway.blocked_desks = {}, {}, {}, {}
        gateway._book_lock = threading.RLock()
        gateway._absorb_order_event(Row({"order_id": "ord-1", "desk_id": "hilibrand", "intent_id": "oi-1", "status": "accepted", "purpose": "entry", "venue": "coinbase"}, 1))
        gateway._absorb_order_event(Row({"order_id": "ord-1", "desk_id": "", "intent_id": None, "status": "accepted", "filled_quantity": "0", "venue": "coinbase"}, 2))
        row = gateway._orders["ord-1"]
        self.assertEqual((row["desk_id"], row["intent_id"], row["purpose"]), ("hilibrand", "oi-1", "entry"))


class UnreadableAnswerTests(unittest.TestCase):
    def test_an_unexpected_exception_after_the_request_blocks_the_desk_like_an_unknown_outcome(self):
        from ltcm.gateway import Gateway
        from ltcm.broker import OrderIntent, Instrument

        class Broker:
            venue = "kalshi"
            def submit(self, intent):
                raise ValueError("2xx with a body that is not JSON")

        seen = {}
        gateway = Gateway.__new__(Gateway)
        gateway._orders, gateway._intent_orders, gateway._venue_orders, gateway.blocked_desks, gateway._seen_fills = {}, {}, {}, {}, set()
        gateway._book_lock, gateway._submitting = threading.RLock(), {}
        gateway._record_order = lambda order, status, at, reason=None: seen.update({"status": status, "reason": reason}) or {"order_id": order.id, "status": status}
        gateway._alert = lambda level, text, at: seen.update({"alert": (level, text)})
        gateway.brokers = {"kalshi": Broker()}
        gateway.route = lambda desk_id, venue: "kalshi"
        intent = OrderIntent.new(desk_id="scholes", instrument=Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="no"), side="buy", quantity=Decimal("1"), order_type="limit", limit_price=Decimal("0.5"), rationale="x", created_at="2026-09-16T08:00:00.000Z")
        row, fills = gateway._submit(intent, "2026-09-16T08:00:00.000Z")
        self.assertEqual((row["status"], fills), ("unknown", []))
        self.assertEqual(gateway.blocked_desks.get("scholes"), row["order_id"])
        self.assertEqual(seen["alert"][0], "critical")
        self.assertIn("ValueError", seen["reason"])


class SoldYesReportedAsBoughtNoTests(SettlementCase):
    """Sept 17, 2026: Kalshi reported the floor's stop that sold 34 YES at 15 cents as 34 NO bought
    at 85. The ledger held both legs, the venue neither, and the stop was re-sent every few minutes."""

    def test_the_fill_lands_on_the_leg_its_order_sold(self):
        self.hold(CPI_YES, quantity="34", price="0.29")
        stop = OrderIntent.new(desk_id=DESK, instrument=CPI_YES, side="sell", quantity="34", order_type="market",
                               rationale="floor exit", created_at=NOW, session_id=None,
                               purpose="exit", exit_reason="stop", exit_of="oi-entry")
        order = Order.from_intent(stop, venue="kalshi")
        order.broker_order_id = "01a0acb0-venue"
        self.gateway._record_order(order, status="accepted", at=NOW)
        as_reported = Fill(id="072219b3", order_id="01a0acb0-venue", desk_id="", instrument=CPI_NO, side="buy",
                           quantity=Decimal("34"), price=Decimal("0.85"), fee=Decimal("0.3035"), at="2026-09-14T16:00:00.000Z")
        self.kalshi._fills.append(as_reported)
        written = self.gateway.ingest_fills("kalshi")
        self.assertEqual(len(written), 1)
        self.assertEqual((written[0]["side"], written[0]["instrument"]["right"], written[0]["price"]), ("sell", "yes", "0.15"))
        positions = self.ledger.state("2026-09-14T16:01:00.000Z").positions
        self.assertNotIn(CPI_NO.key, positions)
        self.assertEqual(positions.get(CPI_YES.key).quantity if CPI_YES.key in positions else Decimal(0), Decimal(0))

    def test_a_fill_already_on_its_orders_leg_is_untouched(self):
        buy_no = OrderIntent.new(desk_id=DESK, instrument=CPI_NO, side="buy", quantity="10", order_type="limit",
                                 limit_price="0.90", rationale="favorite", created_at=NOW, session_id="s")
        order = Order.from_intent(buy_no, venue="kalshi")
        order.broker_order_id = "vx-no-bid"
        self.gateway._record_order(order, status="accepted", at=NOW)
        self.kalshi._fills.append(Fill(id="f-no", order_id="vx-no-bid", desk_id="", instrument=CPI_NO, side="buy",
                                       quantity=Decimal("10"), price=Decimal("0.90"), fee=Decimal("0"), at="2026-09-14T16:00:00.000Z"))
        written = self.gateway.ingest_fills("kalshi")
        self.assertEqual((written[0]["side"], written[0]["instrument"]["right"], written[0]["price"]), ("buy", "no", "0.90"))


class FloorEventExposureTests(GatewayCase):
    """Sept 17, 2026: `mullins` and `mullins-4` run nearly the same favorites settings and could each
    put 3.5% of the floor on one market. The gateway now sums every live desk's book for the rule."""

    BTC = "KXBTCD-26SEP1717-T117999.99"
    ETH = "KXETHD-26SEP1717-T4199.99"
    CLUSTER = "cluster:crypto:2026-09-17T21"

    def setUp(self):
        super().setUp()
        data = copy.deepcopy(SAMPLE)
        data["venues"] = ["kalshi"]
        data["instruments"] = {**data["instruments"], "asset_classes": ["event"], "deny": []}
        data["limits"] = {**data["limits"], "max_order_notional_pct": "1", "max_position_pct": "1", "max_gross_pct": "4"}
        allocations = {}
        for desk_id, mode, usd in (("mullins", "live", "500"), ("mullins-4", "live", "479"), ("mullins-2", "shadow", "500")):
            self.gateway.manifests[desk_id] = DeskManifest.from_dict({**data, "id": desk_id, "family": "kalshi", "capital": {"mode": mode, "usd": usd}})
            self.gateway.ledgers[desk_id] = DeskLedger(self.log, desk_id)
            allocations[desk_id] = usd
        self.log.append("committee", "committee.allocation", {"allocations": allocations, "reasons": {}}, at="2026-09-14T12:00:00.000Z")
        self.gateway.event_rules = {"min_event_price": Decimal("0.15"), "max_event_market_pct": Decimal("0.15"),
                                    "max_event_market_floor_pct": Decimal("0.035"), "max_event_cluster_floor_pct": Decimal("0.08")}
        self.kalshi = FakeBroker(caps={"event", "limit"}, instant_fill=False)
        self.kalshi.venue = "kalshi"
        self.gateway.brokers["kalshi"] = self.kalshi
        self.gateway._quote = lambda instrument, desk_id=None: Quote(instrument, Decimal("0.89"), Decimal("0.91"), Decimal("0.90"), NOW, "kalshi", False)

    def leg(self, ticker, right="no"):
        return Instrument("event", ticker, "kalshi", market_id=ticker, right=right)

    def hold(self, desk_id, ticker, quantity, price="0.90", right="no"):
        tag = f"fl-{desk_id}-{ticker}-{right}"
        self.log.append("broker:kalshi", "broker.fill", {
            "id": tag, "fill_id": tag, "order_id": "ord-" + tag, "desk_id": desk_id, "instrument": self.leg(ticker, right).to_dict(),
            "side": "buy", "quantity": quantity, "price": price, "fee": "0", "at": "2026-09-14T13:00:00.000Z", "venue": "kalshi",
        }, id="fill:kalshi:" + tag, at="2026-09-14T13:00:00.000Z")

    def buy(self, desk_id, ticker, quantity, price="0.90", nonce=None):
        return OrderIntent.new(desk_id=desk_id, instrument=self.leg(ticker), side="buy", quantity=quantity, order_type="limit",
                               limit_price=price, rationale="favorite", created_at=NOW, session_id="s", nonce=nonce)

    def rest(self, intent):
        order = Order.from_intent(intent, venue="kalshi")
        order.broker_order_id = "vx-" + intent.id[-6:]
        self.gateway._record_order(order, status="accepted", at=NOW)

    def test_the_context_sums_every_live_desks_held_legs_and_working_buys_and_no_shadow_book(self):
        self.hold("mullins", self.BTC, "5")                      # $4.50
        self.hold("mullins-4", self.BTC, "20")                   # $18.00
        self.hold("mullins-4", self.BTC, "10", "0.10", "yes")    # $1.00, the other leg
        self.rest(self.buy("mullins-4", self.ETH, "10"))         # $9.00 resting
        self.hold("mullins-2", self.BTC, "100")                  # shadow: never counted
        self.rest(self.buy("mullins-2", self.ETH, "50"))
        ctx = self.gateway.risk_context(self.buy("mullins", self.BTC, "15"), NOW)
        self.assertEqual(ctx.floor_event_exposure, {self.BTC: Decimal("23.50"), self.ETH: Decimal("9.00"), self.CLUSTER: Decimal("32.50")})
        self.assertEqual(ctx.max_event_cluster_floor_pct, Decimal("0.08"))
        self.assertEqual(self.gateway.risk_context(self.buy("mullins-2", self.BTC, "15"), NOW).floor_event_exposure, {}, "a shadow desk's order reads none of it")
        sell = OrderIntent.new(desk_id="mullins", instrument=self.leg(self.BTC), side="sell", quantity="5", order_type="limit",
                               limit_price="0.89", rationale="exit", created_at=NOW, session_id="s")
        self.assertEqual(self.gateway.risk_context(sell, NOW).floor_event_exposure, {}, "nor a sell")

    def test_a_live_desk_is_refused_what_another_live_desk_already_holds_and_a_shadow_desk_is_not(self):
        self.hold("mullins-4", self.BTC, "25")  # $22.50 on the market
        result = self.gateway.propose(self.buy("mullins", self.BTC, "15"), NOW)  # $13.50 more: $36 of a $34.26 cap
        self.assertFalse(result["approved"])
        self.assertTrue(any("across the live desks" in r for r in result["reasons"]), result["reasons"])
        self.assertEqual(self.kalshi.submitted, [])
        small = self.gateway.propose(self.buy("mullins", self.BTC, "10", nonce="small"), NOW)  # $9: $31.50
        self.assertTrue(small["approved"], small["reasons"])
        again = self.gateway.propose(self.buy("mullins-4", self.BTC, "5", nonce="after"), NOW)  # the first desk's resting bid counts
        self.assertFalse(again["approved"])
        self.assertTrue(any("would put 36.00 at risk across the live desks" in r for r in again["reasons"]), again["reasons"])
        shadow = self.gateway.propose(self.buy("mullins-2", self.BTC, "15", nonce="shadow"), NOW)
        self.assertFalse(any("across the live desks" in r for r in shadow["reasons"]), shadow["reasons"])

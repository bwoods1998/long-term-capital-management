"""The Sept 16, 2026 concurrency audit, one regression per fix.

Each case forces its interleaving with a barrier (an event a fake venue or sandbox waits on) or a
held lock, rather than hoping a thread race happens: with the fix the interleaving is refused or
serialized every time, without it the bad outcome follows every time (or, for the few cases that
show a lock is honoured, as soon as the other thread gets a few milliseconds).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Fill, Order, OrderIntent, Quote, UnknownOutcome
from ltcm.events import Event, EventLog
from ltcm.exits import ExitBook
from ltcm.gateway import Gateway
from ltcm.ledger import DeskLedger
from ltcm.manifest import DeskManifest
from ltcm.risk import RiskEngine
from ltcm.sim import ShadowBook
from ltcm.strategies import Strategies
from ltcm.tests.test_exits import ClockedBroker, entry
from ltcm.tests.test_gateway import AAPL, DESK, NOW, FakeBroker, GatewayCase
from ltcm.tests.test_manifest import SAMPLE
from ltcm.tests.test_service import ServiceCase
from ltcm.tests.test_strategies import INTENT, FakeManager, FakeService, Run, manifest as strategy_manifest

#: The most a thread that must finish is given.
WAIT = 5.0
#: How long a thread that must be waiting is watched.
HELD = 0.2

RELAXED = {"max_position_pct": "1.0", "max_gross_pct": "1.0", "max_order_notional_pct": "1.0", "max_daily_loss_pct": "0.10", "max_orders_per_day": 20}


def relaxed(**changes) -> DeskManifest:
    data = copy.deepcopy(SAMPLE)
    data["limits"] = {**RELAXED, **changes.pop("limits", {})}
    data.update(changes)
    return DeskManifest.from_dict(data)


def in_thread(work) -> tuple[threading.Thread, dict]:
    out: dict = {}

    def run() -> None:
        try:
            out["result"] = work()
        except BaseException as exc:  # surfaced by the assertions
            out["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, out


class GatedBroker(FakeBroker):
    """A venue whose next `gated` submissions wait at the door until the test opens it."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gated = 0
        self.entered = threading.Event()
        self.gate = threading.Event()

    def submit(self, intent):
        if self.gated > 0:
            self.gated -= 1
            self.entered.set()
            self.gate.wait(WAIT)
        return super().submit(intent)


# ---------------------------------------------------------------------------- the event log
class EventLogReadTests(unittest.TestCase):
    """events-log-1/2, gateway-money-1, service-state-X1, books-feeds-exits-1."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = EventLog(Path(self.tmp.name) / "events.sqlite")
        self.addCleanup(self.log.close)
        self.log.append("ops", "ops.alert", {"level": "info", "text": "one"}, id="a1")

    def test_a_reader_never_sees_an_append_that_is_then_rolled_back(self):
        done = threading.Event()
        seen: dict = {}

        def reader():
            seen["read"] = [e.seq for e in self.log.read(after=0)]
            seen["latest"] = self.log.latest_seq()
            done.set()

        with self.log._lock:  # an append between BEGIN and ROLLBACK, on the shared connection
            self.log._db.execute("BEGIN IMMEDIATE")
            self.log._db.execute(
                "INSERT INTO events (id, stream, kind, at, public, payload, previous_hash, digest)"
                " VALUES ('x', 'ops', 'ops.alert', '2026-09-16T00:00:00.000Z', 1, '{}', 'genesis', 'dx')"
            )
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            finished_inside = done.wait(HELD)
            self.log._db.execute("ROLLBACK")
        thread.join(WAIT)
        self.assertFalse(finished_inside, "a read waits for the append in progress to end")
        self.assertEqual(seen, {"read": [1], "latest": 1}, "the rolled-back row (and its seq) was never seen")
        reused = self.log.append("ops", "ops.alert", {"level": "info", "text": "two"}, id="a2")
        self.assertEqual(reused.seq, 2)

    def test_every_read_takes_the_log_lock(self):
        reads = {
            "get": lambda: self.log.get("a1"),
            "last": lambda: self.log.last("ops"),
            "count": lambda: self.log.count(),
            "count_stream": lambda: self.log.count("ops"),
            "streams": lambda: self.log.streams(),
            "iter_all": lambda: list(self.log.iter_all()),
        }
        for name, read in reads.items():
            with self.subTest(read=name):
                with self.log._lock:
                    thread, out = in_thread(read)
                    thread.join(HELD / 2)
                    self.assertTrue(thread.is_alive(), f"{name} ran on the shared connection without the lock")
                thread.join(WAIT)
                self.assertNotIn("error", out)

    def test_a_ledger_never_folds_a_row_twice_or_takes_a_cursor_that_is_not_a_seq(self):
        class Tape:
            def __init__(self, rows):
                self.rows = rows

            def read(self, *, after=0, limit=2000, **_):
                return [r for r in self.rows if r.seq is None or r.seq > after][:limit]

        def allocation(seq, usd):
            return Event(seq, f"e{seq}", "committee", "committee.allocation", "2026-09-16T00:00:00.000Z", True,
                         {"allocations": {DESK: usd}}, "", "")

        # What two readers on one connection handed a fold: a row from behind the cursor, and a
        # row with no seq at all.
        tape = Tape([allocation(1, "100"), allocation(None, "999"), allocation(2, "300")])
        ledger = DeskLedger(tape, DESK)
        state = ledger.state("2026-09-16T00:00:01.000Z")
        self.assertEqual((state.allocation, state.seq), (Decimal("300"), 2))
        tape.rows.append(allocation(1, "100"))
        self.assertEqual(ledger.state("2026-09-16T00:00:02.000Z").allocation, Decimal("300"))


class UntilFoldTests(unittest.TestCase):
    """events-log-3: a settlement stamped before `until` and appended after a later event."""

    def test_a_late_appended_settlement_counts_in_a_trailing_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / "events.sqlite")
            try:
                log.append("committee", "committee.allocation", {"allocations": {DESK: "100"}}, at="2026-09-16T11:00:00.000Z")
                log.append("broker:shadow", "broker.fill", {"fill_id": "b", "desk_id": DESK, "instrument": AAPL.to_dict(), "side": "buy",
                           "quantity": "1", "price": "50", "fee": "0"}, id="fill:b", at="2026-09-16T11:30:00.000Z")
                log.append("ops", "ops.alert", {"level": "info", "text": "a worker's alert"}, at="2026-09-16T12:00:02.000Z")
                log.append("broker:shadow", "broker.fill", {"fill_id": "s", "desk_id": DESK, "instrument": AAPL.to_dict(), "side": "sell",
                           "quantity": "1", "price": "80", "fee": "0"}, id="fill:s", at="2026-09-16T11:59:20.000Z")
                state = DeskLedger(log, DESK, until="2026-09-16T12:00:00.000Z").state("2026-09-16T12:00:00.000Z")
                self.assertEqual(state.positions, {})
                self.assertEqual(state.realized_pnl, Decimal("30"))
            finally:
                log.close()


# ---------------------------------------------------------------------------- the gateway
class InflightTests(GatewayCase):
    """gateway-money-2 and books-feeds-exits-5: two proposals of one desk at once."""

    def setUp(self):
        super().setUp()
        self.gateway.manifests[DESK] = relaxed()
        self.broker = GatedBroker()
        self.gateway.brokers["shadow"] = self.broker

    def test_a_proposal_in_flight_commits_its_cash_to_the_next_one(self):
        self.fund("100", at="2026-09-14T13:00:00.000Z")
        self.broker.gated = 1
        thread, first = in_thread(lambda: self.gateway.propose(self.intent(quantity="0.6", nonce="a"), NOW))
        self.assertTrue(self.broker.entered.wait(WAIT))
        second = self.gateway.propose(self.intent(quantity="0.6", nonce="b"), NOW)
        self.broker.gate.set()
        thread.join(WAIT)
        self.assertTrue(first["result"]["approved"], first)
        self.assertFalse(second["approved"])
        self.assertTrue(any("insufficient desk cash" in r for r in second["reasons"]), second["reasons"])
        self.assertEqual(len(self.broker.submitted), 1, "$60.60 twice is not sent on a $100 desk")
        self.assertEqual(self.gateway.inflight(DESK), 0)

    def test_a_proposal_in_flight_counts_against_the_daily_order_cap(self):
        self.gateway.manifests[DESK] = relaxed(limits={"max_orders_per_day": 1})
        self.broker.gated = 1
        thread, first = in_thread(lambda: self.gateway.propose(self.intent(quantity="0.5", nonce="a"), NOW))
        self.assertTrue(self.broker.entered.wait(WAIT))
        second = self.gateway.propose(self.intent(quantity="0.5", nonce="b"), NOW)
        self.broker.gate.set()
        thread.join(WAIT)
        self.assertTrue(first["result"]["approved"], first)
        self.assertIn("desk reached 1 orders today", second["reasons"])

    def test_a_position_is_sold_once_while_a_sell_is_in_flight(self):
        self.assertTrue(self.gateway.propose(self.intent(quantity="2", nonce="buy"), NOW)["approved"])
        self.broker.gated = 1
        thread, first = in_thread(lambda: self.gateway.propose(self.intent(side="sell", quantity="2", nonce="s1"), NOW))
        self.assertTrue(self.broker.entered.wait(WAIT))
        second = self.gateway.propose(self.intent(side="sell", quantity="2", nonce="s2"), NOW)
        self.broker.gate.set()
        thread.join(WAIT)
        self.assertTrue(first["result"]["approved"], first)
        self.assertFalse(second["approved"])
        self.assertTrue(any("sell exceeds position" in r for r in second["reasons"]), second["reasons"])
        self.assertEqual(self.ledger.state(NOW).positions, {}, "sold 2 of 2, not 4")

    def test_a_resting_sell_already_offers_the_position(self):
        self.assertTrue(self.gateway.propose(self.intent(quantity="2", nonce="buy"), NOW)["approved"])
        self.broker.instant_fill = False
        offer = self.gateway.propose(self.intent(side="sell", quantity="2", order_type="limit", limit_price="100", nonce="offer"), NOW)
        self.assertEqual(offer["status"], "accepted")
        again = self.gateway.propose(self.intent(side="sell", quantity="1", nonce="again"), NOW)
        self.assertFalse(again["approved"])
        self.gateway.cancel(DESK, offer["order_id"], NOW)
        self.assertTrue(self.gateway.propose(self.intent(side="sell", quantity="1", nonce="after"), NOW)["approved"])


class LiveVenue(FakeBroker):
    """A live venue whose fill is on its tape (named by the venue's order id, no desk) before
    the submission's answer reaches the floor."""

    venue = "alpaca"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.entered = threading.Event()
        self.gate = threading.Event()

    def submit(self, intent):
        order = Order.from_intent(intent, venue=self.venue)
        order.broker_order_id = "vx-live-1"
        order.submitted_at = intent.created_at
        order.status = "filled"
        order.filled_quantity = order.quantity
        order.average_price = self.price
        self.orders[order.id] = order
        self._fills.append(Fill("venue-fill-1", "vx-live-1", "", order.instrument, order.side, order.quantity, self.price, Decimal("0.01"), NOW))
        self.submitted.append(intent.id)
        self.entered.set()
        self.gate.wait(WAIT)
        return order


class LiveGatewayCase(GatewayCase):
    def live_gateway(self, venue):
        live = relaxed(capital={"mode": "live", "usd": "1000"})
        return Gateway(self.log, RiskEngine(), {"alpaca": venue, "shadow": self.broker}, {DESK: self.ledger},
                       manifests={DESK: live}, kill_switch_path=self.kill)


class AttributionTests(LiveGatewayCase):
    """gateway-money-3: a fill swept by another thread before the submission is recorded."""

    def test_a_fill_swept_while_its_order_is_in_flight_still_reaches_the_desk(self):
        venue = LiveVenue()
        gateway = self.live_gateway(venue)
        thread, out = in_thread(lambda: gateway.propose(self.intent(quantity="1"), NOW))
        self.assertTrue(venue.entered.wait(WAIT))
        self.assertEqual(gateway.ingest_fills("alpaca"), [], "the tick's sweep leaves a fill it cannot place yet")
        venue.gate.set()
        thread.join(WAIT)
        self.assertTrue(out["result"]["approved"], out)
        fill = self.log.get("fill:alpaca:venue-fill-1")
        self.assertIsNotNone(fill)
        self.assertEqual(fill.payload.get("desk_id"), DESK)
        self.assertEqual(self.ledger.state(NOW).positions[AAPL.key].quantity, Decimal("1"))

    def test_a_fill_already_on_the_tape_with_other_content_never_escapes_the_sweep(self):
        venue = FakeBroker()
        venue.venue = "alpaca"
        gateway = self.live_gateway(venue)
        self.log.append("broker:alpaca", "broker.fill", {"fill_id": "f9", "note": "written by another sweep"}, id="fill:alpaca:f9")
        venue._fills.append(Fill("f9", "vx-9", "", AAPL, "buy", Decimal("1"), Decimal("100"), Decimal("0"), NOW))
        self.assertEqual(gateway.ingest_fills("alpaca"), [])
        self.assertEqual(gateway.ingest_fills("alpaca"), [])


class UnknownOutcomeVenue(FakeBroker):
    venue = "alpaca"

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.gate = threading.Event()
        self.calls = 0
        self.never_placed: set[str] = set()

    def submit(self, intent):
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            self.gate.wait(WAIT)
        raise UnknownOutcome("timed out after the request was sent")

    def get_order(self, order_id):
        if order_id in self.never_placed:
            raise LookupError("no such order")
        raise ConnectionError("the venue did not answer")


class BlockedDeskTests(LiveGatewayCase):
    """gateway-money-4: two unknown outcomes on one desk; reconciling one must not free the desk."""

    def test_the_desk_stays_blocked_until_every_unknown_order_is_resolved(self):
        venue = UnknownOutcomeVenue()
        gateway = self.live_gateway(venue)
        first_intent = self.intent(quantity="0.5", nonce="first")
        second_intent = self.intent(quantity="0.5", nonce="second")
        thread, _ = in_thread(lambda: gateway.propose(first_intent, NOW))
        self.assertTrue(venue.entered.wait(WAIT))
        self.assertEqual(gateway.propose(second_intent, NOW)["status"], "unknown")
        venue.gate.set()
        thread.join(WAIT)
        first_id = Order.from_intent(first_intent, venue="alpaca").id
        second_id = Order.from_intent(second_intent, venue="alpaca").id
        venue.never_placed.add(first_id)
        gateway.reconcile("alpaca", NOW)
        self.assertEqual(gateway.blocked_desks, {DESK: second_id})
        self.assertTrue(gateway.propose(self.intent(quantity="0.5", nonce="third"), NOW)["blocked"])
        venue.never_placed.add(second_id)
        gateway.reconcile("alpaca", NOW)
        self.assertEqual(gateway.blocked_desks, {})


class PromotionWindowTests(GatewayCase):
    """gateway-money-5, service-state-2/3, books-feeds-exits-3: routing and risk read one mode."""

    def setUp(self):
        super().setUp()
        self.venue = FakeBroker()
        self.venue.venue = "alpaca"
        self.gateway.brokers["alpaca"] = self.venue
        self.gateway.manifests_carry_mode = True

    def promote(self):
        self.log.append("evolution", "evolution.promoted", {"desk_id": DESK, "from": "shadow", "to": "live", "score": {}},
                        id="promoted:" + DESK, at="2026-09-14T13:00:00.000Z")

    def test_a_logged_promotion_proposes_nothing_until_the_owner_moves_the_manifest(self):
        self.promote()
        result = self.gateway.propose(self.intent(quantity="1", nonce="during"), NOW)
        self.assertFalse(result["approved"])
        self.assertIn("capital mode is changing", result["reasons"][0])
        self.assertEqual((self.venue.submitted, self.broker.submitted), ([], []))
        self.gateway.manifests[DESK] = dataclasses.replace(self.manifest, capital_mode="live")
        self.assertTrue(self.gateway.propose(self.intent(quantity="1", nonce="after"), NOW)["approved"])
        self.assertEqual(len(self.venue.submitted), 1)

    def test_a_promotion_applied_while_a_proposal_is_checked_is_not_routed_to_the_venue(self):
        quote = self.gateway._quote

        def promoted_meanwhile(instrument, desk_id=None):
            self.promote()
            self.gateway.manifests[DESK] = dataclasses.replace(self.manifest, capital_mode="live")
            return quote(instrument, desk_id)

        self.gateway._quote = promoted_meanwhile
        result = self.gateway.propose(self.intent(quantity="1"), NOW)
        self.assertFalse(result["approved"])
        self.assertEqual(self.venue.submitted, [], "checked as shadow, never sent as live")
        self.assertEqual(self.broker.submitted, [])


class ServiceCapitalModeTests(ServiceCase):
    def test_the_gateway_goes_live_only_after_the_sleeve_is_set_up(self):
        seen = {}
        begin = self.service._begin_live

        def spy(manifest):
            seen["gateway_live"] = self.service.gateway.live_desk(DESK)
            seen["moving"] = self.service.gateway._mode_moving(DESK)
            return begin(manifest)

        self.service._begin_live = spy
        self.service.log.append("evolution", "evolution.promoted", {"desk_id": DESK, "from": "shadow", "to": "live", "score": {}},
                                id="promoted:" + DESK, at=self.service.now())
        self.service._apply_capital_modes()
        self.assertEqual(seen, {"gateway_live": False, "moving": True})
        self.assertTrue(self.service.gateway.live_desk(DESK))
        self.assertFalse(self.service.gateway._mode_moving(DESK))

    def test_a_demoted_desk_has_its_book_before_the_gateway_routes_to_it(self):
        self.write_manifest(DESK, capital={"mode": "live", "usd": "1000"})
        self.service.close()
        self.service = self.build(live_venues=[])
        seen = {}
        make = self.service._make_shadow_book

        def spy(manifest, path):
            seen["gateway_live"] = self.service.gateway.live_desk(DESK)
            return make(manifest, path)

        self.service._make_shadow_book = spy
        self.service.log.append("evolution", "evolution.promoted", {"desk_id": DESK, "from": "live", "to": "shadow", "reason": "breach"},
                                id="demoted:" + DESK, at=self.service.now())
        self.service._apply_capital_modes()
        self.assertEqual(seen, {"gateway_live": True})
        self.assertFalse(self.service.gateway.live_desk(DESK))

    def test_a_shadow_desk_without_a_book_is_refused_not_blocked(self):
        from ltcm.broker import RejectedOrder
        from ltcm.service import _ShadowRouter

        with self.assertRaises(RejectedOrder):
            _ShadowRouter({}, {}).submit(OrderIntent.new(desk_id="nobody", instrument=AAPL, side="buy", quantity="1",
                                                         rationale="x", created_at=NOW))


class FillCursorTests(GatewayCase):
    """gateway-money-6, books-feeds-exits-7: fills are not ingested in the order they are stamped."""

    def test_a_fill_stamped_before_one_already_swept_is_still_ingested(self):
        def fill(fill_id, at):
            return Fill(fill_id, "ord-" + fill_id, DESK, AAPL, "buy", Decimal("1"), Decimal("100"), Decimal("0"), at)

        self.broker._fills = [fill("later", "2026-09-14T14:30:05.000Z")]
        self.assertEqual(len(self.gateway.ingest_fills("shadow")), 1)
        self.broker._fills.append(fill("earlier", "2026-09-14T14:30:00.000Z"))  # a worker's fill, swept late
        self.assertEqual([f["fill_id"] for f in self.gateway.ingest_fills("shadow")], ["earlier"])
        self.assertEqual(self.gateway.ingest_fills("shadow"), [])
        self.assertEqual(self.ledger.state(NOW).positions[AAPL.key].quantity, Decimal("2"))


class OrderBookSnapshotTests(GatewayCase):
    """books-feeds-exits-10, service-state-7, gateway-money-8: the book is read under its lock."""

    def test_reading_the_orders_waits_for_a_writer_of_the_book(self):
        self.gateway.propose(self.intent(quantity="1"), NOW)
        with self.gateway._book_lock:  # `_record_order` inserting on another thread
            thread, out = in_thread(lambda: self.gateway.open_orders())
            thread.join(HELD)
            self.assertTrue(thread.is_alive(), "the feed thread's read iterated the book mid-insert")
        thread.join(WAIT)
        self.assertEqual(out.get("result"), [])


# ---------------------------------------------------------------------------- exits
class ExitConcurrencyTests(GatewayCase):
    def setUp(self):
        super().setUp()
        self.broker = ClockedBroker()
        self.gateway.brokers["shadow"] = self.broker
        self.book = ExitBook(self.log, self.gateway, {DESK: self.ledger}, {DESK: self.manifest},
                             quote=self.broker.quote, clock=lambda: 0.0, check_seconds=0, retry_seconds=300)
        self.gateway.exits = self.book

    def test_a_resting_entry_keeps_its_plan_until_it_fills(self):
        """books-feeds-exits-4."""
        self.broker.instant_fill = False
        opened = self.gateway.propose(entry(order_type="limit", limit_price="100"), NOW)
        self.assertEqual(opened["status"], "accepted", opened)
        self.assertEqual(self.book.tick("2026-09-14T14:31:00.000Z"), [])
        self.assertEqual(len(self.book.plans()), 1, "flat because it rests, not because it closed")
        self.broker.complete(opened["order_id"], at="2026-09-14T14:32:00.000Z", price="100")
        self.gateway.poll_orders("2026-09-14T14:32:00.000Z")
        self.broker.instant_fill = True
        self.broker.price = Decimal("94")
        outcomes = self.book.tick("2026-09-14T14:33:00.000Z")
        self.assertEqual([o["reason"] for o in outcomes], ["stop"])
        self.assertTrue(outcomes[0]["approved"], outcomes)

    def test_an_exit_replaces_the_desks_own_resting_offer(self):
        self.assertTrue(self.gateway.propose(entry(), NOW)["approved"])
        self.broker.instant_fill = False
        offer = self.gateway.propose(OrderIntent.new(desk_id=DESK, instrument=AAPL, side="sell", quantity="2", order_type="limit",
                                                     limit_price="101", rationale="offer the position", created_at=NOW, session_id="s2"), NOW)
        self.assertEqual(offer["status"], "accepted", offer)
        self.broker.instant_fill = True
        self.broker.price = Decimal("94")
        outcomes = self.book.tick("2026-09-14T14:33:00.000Z")
        self.assertTrue(outcomes[0]["approved"], outcomes)
        self.assertIn(offer["order_id"], self.broker.cancelled)
        self.assertEqual(self.ledger.state("2026-09-14T14:34:00.000Z").positions, {})


# ---------------------------------------------------------------------------- shadow books
class StubData:
    def quote(self, instrument):
        return Quote(instrument, Decimal("99"), Decimal("101"), Decimal("100"), NOW, "stub", False)


class ShadowBookReadTests(unittest.TestCase):
    """books-feeds-exits-2: a read on the book's shared connection waits for its writer."""

    def test_every_read_takes_the_books_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = ShadowBook(Path(tmp) / "book.sqlite", market_venue="alpaca", data=StubData(), clock=lambda: 1_789_000_000.0, initial_cash="1000")
            try:
                order = book.submit(OrderIntent.new(desk_id=DESK, instrument=AAPL, side="buy", quantity="1", order_type="limit",
                                                    limit_price="90", rationale="rest", created_at=NOW))
                reads = {
                    "get_order": lambda: book.get_order(order.id),
                    "order_for_intent": lambda: book.order_for_intent(order.intent_id),
                    "open_orders": book.open_orders,
                    "orders": book.orders,
                    "fills": book.fills,
                    "positions": book.positions,
                    "balance": book.balance,
                    "marks": book.marks,
                    "snapshot": book.snapshot,
                }
                for name, read in reads.items():
                    with self.subTest(read=name):
                        with book._lock:
                            thread, out = in_thread(read)
                            thread.join(HELD / 2)
                            self.assertTrue(thread.is_alive(), f"{name} read without the book's lock")
                        thread.join(WAIT)
                        self.assertNotIn("error", out)
            finally:
                book.close()


# ---------------------------------------------------------------------------- service state and loop
class ServiceStateTests(ServiceCase):
    """service-state-1, books-feeds-exits-6: two threads saving the state file at once."""

    def test_a_save_waits_for_a_save_in_progress_and_keeps_its_keys(self):
        read = self.service.state
        inside, go = threading.Event(), threading.Event()

        def slow_state():
            data = read()
            if threading.current_thread().name == "lab-worker":
                inside.set()
                go.wait(WAIT)
            return data

        self.service.state = slow_state
        lab = threading.Thread(target=lambda: self.service._save_state(from_lab=1), name="lab-worker", daemon=True)
        lab.start()
        self.assertTrue(inside.wait(WAIT))
        tick, _ = in_thread(lambda: self.service._save_state(from_tick=1))
        tick.join(HELD)
        go.set()
        lab.join(WAIT)
        tick.join(WAIT)
        saved = read()
        self.assertEqual((saved.get("from_lab"), saved.get("from_tick")), (1, 1))


class RunLoopTests(ServiceCase):
    """service-state-7: a failing health report after a failed tick must not end the loop."""

    def test_the_loop_survives_a_health_report_that_raises(self):
        def fail(*args, **kwargs):
            raise RuntimeError("dictionary changed size during iteration")

        self.service.tick = fail
        self.service.health = fail
        self.service.run(once=True)
        self.assertIn("health failed", self.service.last_error)


# ---------------------------------------------------------------------------- strategies
class StrategyRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = FakeManager()
        self.manifest = strategy_manifest()
        self.service = FakeService(self.manager, {self.manifest.id: self.manifest})
        self.strategies = Strategies(self.service, path=Path(self.temp.name) / "strategies.json", config={"starters": False})
        self.manager.files[self.manifest.id] = {"edge.py": "def decide(kit, params):\n    return []\n"}

    def test_a_strategy_undeployed_while_its_run_is_in_the_sandbox_stays_undeployed(self):
        """strategies-sandbox-1."""
        self.strategies.deploy(self.manifest, "edge", 600, {"min_edge": 0.03})
        row = self.strategies.store.for_desk(self.manifest.id)["edge"]

        def undeployed_meanwhile(desk_id, code):
            self.strategies.undeploy(self.manifest, "edge")  # a session thread, mid-run
            return Run("STRATEGY-RESULT " + json.dumps({"intents": [INTENT]}))

        self.manager.script = undeployed_meanwhile
        self.strategies.run_one(self.manifest, "edge", row, "2026-09-16T04:21:00.000Z")
        self.assertEqual(self.strategies.store.for_desk(self.manifest.id), {})
        self.assertEqual([i for c in self.service.contexts for i in c.intents], [], "its orders were not proposed")
        self.assertEqual(self.strategies.due(self.service.manifests, "2026-09-16T09:00:00.000Z"), [])

    def test_a_desk_promoted_while_its_run_was_in_the_sandbox_is_sized_as_live(self):
        """strategies-sandbox-3."""
        live = strategy_manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        shadow = strategy_manifest(id="scholes", parent_id=None)
        self.manager.files["scholes"] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(shadow, "edge", 600, {})
        row = self.strategies.store.for_desk("scholes")["edge"]
        self.service.manifests = {"scholes": live}  # the promotion landed after dispatch
        self.manager.script = lambda d, c: Run("STRATEGY-RESULT " + json.dumps({"intents": [INTENT]}))
        self.strategies.run_one(shadow, "edge", row, NOW)
        self.assertEqual(self.service.contexts[-1].intents[0].quantity, Decimal("12"), "learning size, not the shadow's")

    def test_a_promotion_never_overwrites_a_desks_own_redeploy(self):
        """strategies-sandbox-4."""
        self.strategies.store.update("scholes", "edge", house=True, deployed_at="t0", params={"min_edge": 0.05}, enabled=True)
        row = self.strategies.store.for_desk("scholes")["edge"]
        self.strategies.store.update("scholes", "edge", house=False, deployed_at="t1", params={"min_edge": 0.08})
        self.assertIsNone(self.strategies.store.patch("scholes", "edge", {"house": row.get("house"), "deployed_at": row.get("deployed_at"), "params": row.get("params")}, params={"min_edge": 0.01}))
        self.assertEqual(self.strategies.store.for_desk("scholes")["edge"]["params"], {"min_edge": 0.08})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

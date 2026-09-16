"""Exit plans: stated with the entry, published, and enforced by the floor (leap: exits)."""

from __future__ import annotations

import unittest
from decimal import Decimal

from ltcm.adapters.coinbase import attached_bracket, bracket_refused
from ltcm.broker import Instrument, OrderIntent, RejectedOrder
from ltcm.events import EventLog
from ltcm.exits import ExitBook, ExitPlan
from ltcm.gateway import Gateway
from ltcm.ledger import DeskLedger
from ltcm.manifest import DeskManifest
from ltcm.publish import checkpoint_body
from ltcm.risk import RiskEngine, rule_exit_plan
from ltcm.tests import test_adapters_coinbase as coinbase
from ltcm.tests.test_gateway import AAPL, DESK, NOW, FakeBroker, GatewayCase
from ltcm.tests.test_manifest import SAMPLE
from ltcm.tests.test_risk import context as risk_context
from ltcm.tests.test_service import ServiceCase, moment
from ltcm.tests.test_tools import FakeContext, run, session

BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")
LATER = "2026-09-15T14:30:00.000Z"


def entry(**overrides):
    base = dict(
        desk_id=DESK,
        instrument=AAPL,
        side="buy",
        quantity="2",
        rationale="post-earnings drift on a documented revenue beat, out by Friday",
        created_at=NOW,
        session_id="s1",
        target_price="110",
        stop_price="95",
        time_stop_at=LATER,
    )
    base.update(overrides)
    return OrderIntent.new(**base)


class IntentFieldTests(unittest.TestCase):
    def test_the_plan_rides_on_the_intent_and_round_trips(self):
        intent = entry()
        self.assertTrue(intent.has_exit_plan)
        self.assertEqual(intent.target_price, Decimal("110"))
        self.assertEqual(intent.stop_price, Decimal("95"))
        self.assertEqual(intent.time_stop_at, LATER)
        self.assertEqual(intent.purpose, "entry")
        again = OrderIntent.from_dict(intent.to_dict())
        self.assertEqual(again, intent)
        self.assertEqual(intent.to_dict()["exit_of"], None)

    def test_an_entry_without_a_plan_says_so(self):
        self.assertFalse(entry(target_price=None, stop_price=None, time_stop_at=None).has_exit_plan)

    def test_an_exit_is_its_own_intent_and_names_what_it_closes(self):
        opened = entry()
        closing = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="sell", quantity="2", rationale="floor exit",
            created_at=LATER, nonce="exit:stop", purpose="exit", exit_reason="stop", exit_of=opened.id,
        )
        self.assertNotEqual(closing.id, opened.id)
        self.assertFalse(closing.has_exit_plan)
        # The same trigger noticed again derives the same id: one order, however many ticks.
        twin = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="sell", quantity="2", rationale="floor exit",
            created_at="2026-09-15T14:31:00.000Z", nonce="exit:stop", purpose="exit",
            exit_reason="stop", exit_of=opened.id,
        )
        self.assertEqual(twin.id, closing.id)
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id=DESK, instrument=AAPL, side="sell", quantity="2",
                            rationale="x", created_at=NOW, purpose="exit", exit_reason="stop")
        with self.assertRaises(ValueError):
            entry(stop_price="-1")


class RiskRuleTests(unittest.TestCase):
    def test_a_stop_above_a_buy_or_a_target_below_it_is_refused(self):
        ctx = risk_context()  # quote 99/101/100
        self.assertIn("must be below", rule_exit_plan(entry(stop_price="105", target_price=None), ctx))
        self.assertIn("must be above", rule_exit_plan(entry(target_price="98", stop_price=None), ctx))
        self.assertIsNone(rule_exit_plan(entry(), ctx))

    def test_a_sell_is_checked_the_other_way_round(self):
        ctx = risk_context()
        self.assertIn("must be above", rule_exit_plan(entry(side="sell", stop_price="90", target_price=None), ctx))
        self.assertIn("must be below", rule_exit_plan(entry(side="sell", target_price="120", stop_price=None), ctx))
        self.assertIsNone(rule_exit_plan(entry(side="sell", stop_price="105", target_price="90"), ctx))

    def test_a_limit_entry_is_measured_from_its_own_price(self):
        ctx = risk_context()
        limit = entry(order_type="limit", limit_price="90", stop_price="89", target_price="95")
        self.assertIsNone(rule_exit_plan(limit, ctx))
        inverted = entry(order_type="limit", limit_price="90", stop_price="91", target_price=None)
        self.assertIn("must be below the entry 90", rule_exit_plan(inverted, ctx))

    def test_the_engine_lists_the_inverted_level_and_lets_a_sound_plan_through(self):
        engine = RiskEngine()
        refused = engine.check(entry(stop_price="105"), risk_context())
        self.assertFalse(refused.approved)
        self.assertTrue(any("stop price" in r for r in refused.reasons))
        self.assertTrue(engine.check(entry(quantity="1"), risk_context()).approved)


class ToolTests(unittest.TestCase):
    def arguments(self, **overrides):
        base = {
            "instrument": {"asset_class": "equity", "symbol": "AAPL"},
            "side": "buy",
            "quantity": "2",
            "order_type": "market",
            "rationale": "documented beat",
            "target_price": "110",
            "stop_price": "95",
            "holding_period_hours": 24,
        }
        base.update(overrides)
        return base

    def test_the_plan_reaches_the_intent_and_the_result_says_so(self):
        ctx = FakeContext()
        sess = session()
        out = run("propose_order", self.arguments(), ctx, sess=sess)
        intent = ctx.intents[0]
        self.assertEqual(intent.target_price, Decimal("110"))
        self.assertEqual(intent.stop_price, Decimal("95"))
        self.assertEqual(intent.time_stop_at, "2026-09-16T13:45:00.000Z")  # 24h after the turn
        self.assertEqual(out["exit_plan"], {"target_price": "110", "stop_price": "95",
                                            "time_stop_at": "2026-09-16T13:45:00.000Z"})
        from ltcm import tools

        summary = tools.summarize_result("propose_order", out)
        self.assertIn("exit plan: target 110, stop 95, time stop 2026-09-16T13:45:00.000Z", summary)
        public = tools.public_arguments("propose_order", self.arguments())
        self.assertEqual(public["holding_period_hours"], 24)

    def test_a_bad_holding_period_is_refused_before_anything_is_proposed(self):
        for bad in (0, 721, "24", True):
            ctx = FakeContext()
            out = run("propose_order", self.arguments(holding_period_hours=bad), ctx)
            self.assertIn("error", out, bad)
            self.assertEqual(ctx.intents, [])

    def test_an_order_without_a_plan_still_works(self):
        ctx = FakeContext()
        out = run("propose_order", {k: v for k, v in self.arguments().items()
                                    if k not in ("target_price", "stop_price", "holding_period_hours")}, ctx)
        self.assertTrue(out["approved"])
        self.assertNotIn("exit_plan", out)
        self.assertFalse(ctx.intents[0].has_exit_plan)


class CoinbaseBracketTests(unittest.TestCase):
    def test_both_legs_ride_on_the_entry_and_nothing_less_does(self):
        both = coinbase.intent(target_price="80000", stop_price="70000")
        self.assertEqual(
            attached_bracket(both),
            {"trigger_bracket_gtc": {"limit_price": "80000", "stop_trigger_price": "70000"}},
        )
        self.assertIsNone(attached_bracket(coinbase.intent(stop_price="70000")))
        self.assertIsNone(attached_bracket(coinbase.intent()))
        client, transport, _ = coinbase.make({("POST", coinbase.HOST + coinbase.PREFIX + "/orders"): coinbase.CREATED})
        order = client.submit(both)
        self.assertEqual(transport.last["body"]["attached_order_configuration"],
                         {"trigger_bracket_gtc": {"limit_price": "80000", "stop_trigger_price": "70000"}})
        self.assertNotIn("base_size", transport.last["body"]["attached_order_configuration"]["trigger_bracket_gtc"])
        self.assertIs(order._raw["bracket"], True)

    def test_a_bracket_the_venue_refuses_is_dropped_and_the_entry_goes_bare(self):
        refused = {"success": False, "error_response": {"error": "INVALID_ORDER_SIDE_FOR_ATTACHED_TPSL",
                                                        "message": "attached tpsl not allowed"}}
        answers = [refused, coinbase.CREATED]
        client, transport, _ = coinbase.make(
            {("POST", coinbase.HOST + coinbase.PREFIX + "/orders"): lambda *a, **k: answers.pop(0)}
        )
        order = client.submit(coinbase.intent(target_price="80000", stop_price="70000"))
        self.assertEqual(order.status, "accepted")
        self.assertNotIn("attached_order_configuration", transport.last["body"])
        self.assertIs(order._raw["bracket"], False)
        self.assertTrue(bracket_refused("SINGLE_LEGGED_ATTACHED_ORDER_CONFIGURATION_NOT_ALLOWED"))
        self.assertFalse(bracket_refused("Insufficient balance in source account"))

    def test_an_unrelated_refusal_is_not_retried(self):
        calls = []
        client, transport, _ = coinbase.make(
            {("POST", coinbase.HOST + coinbase.PREFIX + "/orders"): lambda *a, **k: calls.append(1) or coinbase.REFUSED}
        )
        with self.assertRaises(RejectedOrder):
            client.submit(coinbase.intent(target_price="80000", stop_price="70000"))
        self.assertEqual(len(calls), 1)


class ExitPlanTests(unittest.TestCase):
    def test_a_long_exits_at_the_stop_below_the_target_above_or_the_clock(self):
        plan = ExitPlan.from_intent(entry())
        self.assertIsNone(plan.due(Decimal("100"), NOW))
        self.assertEqual(plan.due(Decimal("95"), NOW), "stop")
        self.assertEqual(plan.due(Decimal("94"), NOW), "stop")
        self.assertEqual(plan.due(Decimal("110.5"), NOW), "target")
        self.assertEqual(plan.due(Decimal("100"), LATER), "time_stop")
        self.assertEqual(plan.due(None, LATER), "time_stop")
        self.assertEqual(plan.exit_side, "sell")

    def test_a_short_is_the_mirror_image(self):
        plan = ExitPlan.from_intent(entry(side="sell", stop_price="105", target_price="90"))
        self.assertEqual(plan.due(Decimal("106"), NOW), "stop")
        self.assertEqual(plan.due(Decimal("89"), NOW), "target")
        self.assertIsNone(plan.due(Decimal("100"), NOW))
        self.assertEqual(plan.exit_side, "buy")

    def test_a_venue_native_plan_leaves_the_levels_to_the_venue(self):
        plan = ExitPlan.from_intent(entry(), venue_native=True)
        self.assertIsNone(plan.due(Decimal("50"), NOW))
        self.assertEqual(plan.due(Decimal("50"), LATER), "time_stop")

    def test_the_payload_is_the_contract_shape_and_rebuilds_the_plan(self):
        plan = ExitPlan.from_intent(entry(), created_at=NOW)
        payload = plan.to_payload()
        for key in ("intent_id", "instrument", "target_price", "stop_price", "time_stop_at", "venue_native", "order_ids"):
            self.assertIn(key, payload)
        self.assertEqual(payload["target_price"], "110")
        self.assertEqual(payload["order_ids"], [])
        again = ExitPlan.from_payload(payload, desk_id=DESK, created_at=NOW)
        self.assertEqual(again, plan)


class ClockedBroker(FakeBroker):
    """A fake venue whose fills carry the order's own time, so a same-second exit is not
    hidden behind the entry by the fill cursor the way the shared fake's constant stamp is."""

    def submit(self, intent):
        if self.raises is not None:
            raise self.raises
        self.submitted.append(intent.id)
        existing = self.orders.get("ord-" + intent.id[3:])
        if existing is not None:
            return existing
        from ltcm.broker import Order

        order = Order.from_intent(intent, venue=self.venue)
        order.status = "accepted"
        order.broker_order_id = "vx-" + order.id[-6:]
        order.submitted_at = intent.created_at
        self.orders[order.id] = order
        if self.instant_fill:
            self.complete(order.id, at=intent.created_at)
        return self.orders[order.id]


class RecordingCritic:
    def __init__(self):
        self.asked = []

    def review(self, **kwargs):
        self.asked.append(kwargs["intent"].id)
        from ltcm.critic import CriticReview

        return CriticReview("approve", "fine", "fake")


class ExitBookTests(GatewayCase):
    def setUp(self):
        super().setUp()
        self.broker = ClockedBroker()
        self.gateway.brokers["shadow"] = self.broker
        self.book = ExitBook(
            self.log, self.gateway, {DESK: self.ledger}, {DESK: self.manifest},
            quote=self.broker.quote, clock=lambda: 0.0, check_seconds=0, retry_seconds=300,
        )
        self.gateway.exits = self.book

    def open_position(self, **overrides):
        result = self.gateway.propose(entry(**overrides), NOW)
        self.assertTrue(result["approved"], result["reasons"])
        return result

    def orders_for(self, purpose):
        return [e for e in self.log.read(kind="broker.order", limit=1000) if e.payload.get("purpose") == purpose]

    def test_an_accepted_entry_publishes_its_plan_once(self):
        self.open_position()
        plans = self.log.read(kind="desk.exit_plan", limit=100)
        self.assertEqual(len(plans), 1)
        event = plans[0]
        self.assertEqual(event.stream, f"desk:{DESK}")
        self.assertTrue(event.id.startswith("exitplan:oi-"))
        self.assertEqual(event.payload["target_price"], "110")
        self.assertEqual(event.payload["stop_price"], "95")
        self.assertEqual(event.payload["time_stop_at"], LATER)
        self.assertFalse(event.payload["venue_native"])
        self.assertEqual(len(self.book.plans()), 1)
        # The entry's own intent record carries the plan and its purpose.
        intent_event = self.log.read(kind="desk.intent", limit=10)[0]
        self.assertEqual(intent_event.payload["purpose"], "entry")
        self.assertEqual(intent_event.payload["stop_price"], "95")
        # The order record says what it was for.
        self.assertEqual(self.orders_for("entry")[0].payload["purpose"], "entry")

    def test_a_rejected_entry_leaves_no_plan(self):
        result = self.gateway.propose(entry(quantity="500"), NOW)  # notional beyond the cap
        self.assertFalse(result["approved"])
        self.assertEqual(self.log.read(kind="desk.exit_plan", limit=10), [])

    def test_the_stop_files_one_exposure_reducing_exit_and_the_plan_closes(self):
        self.open_position()
        self.assertEqual(self.book.tick("2026-09-14T14:31:00.000Z"), [])  # mark 99 (bid): quiet
        self.broker.price = Decimal("94")  # bid 93, under the 95 stop
        outcomes = self.book.tick("2026-09-14T14:32:00.000Z")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["reason"], "stop")
        self.assertTrue(outcomes[0]["approved"], outcomes)
        exits = self.orders_for("exit")
        self.assertTrue(exits)
        payload = exits[-1].payload
        self.assertEqual(payload["exit_reason"], "stop")
        self.assertEqual(payload["exit_of"], self.book_intent_id())
        self.assertEqual(payload["side"], "sell")
        self.assertEqual(payload["quantity"], "2")
        self.assertEqual(payload["status"], "filled")
        # The position is gone, the plan is closed, and nothing more is filed.
        self.assertEqual(self.ledger.state("2026-09-14T14:33:00.000Z").positions, {})
        self.assertEqual(self.book.plans(), {})
        self.assertEqual(self.book.tick("2026-09-14T14:40:00.000Z"), [])
        self.assertEqual(len(self.broker.submitted), 2)

    def book_intent_id(self):
        return next(iter(self.log.read(kind="desk.exit_plan", limit=10))).payload["intent_id"]

    def test_the_target_files_an_exit_too(self):
        self.open_position()
        self.broker.price = Decimal("112")  # bid 111, over the 110 target
        outcomes = self.book.tick("2026-09-14T14:32:00.000Z")
        self.assertEqual([o["reason"] for o in outcomes], ["target"])
        self.assertEqual(self.orders_for("exit")[-1].payload["exit_reason"], "target")

    def test_the_time_stop_exits_at_market_when_the_clock_passes(self):
        self.open_position(target_price=None, stop_price=None)
        self.assertEqual(self.book.tick("2026-09-15T14:29:00.000Z"), [])
        outcomes = self.book.tick("2026-09-15T14:30:00.000Z")
        self.assertEqual([o["reason"] for o in outcomes], ["time_stop"])
        row = self.orders_for("exit")[-1].payload
        self.assertEqual(row["exit_reason"], "time_stop")
        self.assertEqual(row["order_type"], "market")

    def test_a_refused_exit_is_retried_on_a_slow_cadence_with_the_same_intent(self):
        self.open_position()
        self.broker.raises = RejectedOrder("venue closed")
        self.broker.price = Decimal("90")
        first = self.book.tick("2026-09-14T14:32:00.000Z")
        self.assertFalse(first[0]["approved"])
        self.assertEqual(self.book.tick("2026-09-14T14:34:00.000Z"), [])  # inside the retry window
        self.broker.raises = None
        second = self.book.tick("2026-09-14T14:38:00.000Z")
        self.assertTrue(second[0]["approved"])
        self.assertEqual(second[0]["exit_intent_id"], first[0]["exit_intent_id"])

    def test_a_position_closed_by_the_desk_itself_retires_its_plan(self):
        self.open_position()
        closing = OrderIntent.new(desk_id=DESK, instrument=AAPL, side="sell", quantity="2",
                                  rationale="taking it off", created_at="2026-09-14T14:31:00.000Z",
                                  session_id="s2")
        self.assertTrue(self.gateway.propose(closing, "2026-09-14T14:31:00.000Z")["approved"])
        self.broker.price = Decimal("90")
        self.assertEqual(self.book.tick("2026-09-14T14:32:00.000Z"), [])
        self.assertEqual(self.book.plans(), {})

    def test_a_venue_native_plan_only_gets_the_time_stop_from_the_floor(self):
        intent = entry()
        plan = self.book.record_for(intent, {"status": "accepted", "venue": "coinbase", "bracket": True}, NOW)
        self.assertTrue(plan.venue_native)
        self.assertTrue(self.log.read(kind="desk.exit_plan", limit=10)[0].payload["venue_native"])
        self.assertIsNone(plan.due(Decimal("50"), NOW))
        self.assertEqual(plan.due(Decimal("50"), LATER), "time_stop")

    def test_an_exit_never_goes_to_the_critic(self):
        live = DeskManifest.from_dict({**SAMPLE, "capital": {"mode": "live", "usd": "1000"}})
        critic = RecordingCritic()
        gateway = Gateway(self.log, RiskEngine(), {"shadow": self.broker, "alpaca": self.broker},
                          {DESK: self.ledger}, manifests={DESK: live}, kill_switch_path=self.kill, critic=critic)
        opened = gateway.propose(entry(quantity="1"), NOW)
        self.assertTrue(opened["approved"], opened["reasons"])
        self.assertEqual(len(critic.asked), 1)
        closing = OrderIntent.new(desk_id=DESK, instrument=AAPL, side="sell", quantity="1",
                                  rationale="floor exit", created_at=LATER, nonce="exit:time_stop",
                                  purpose="exit", exit_reason="time_stop", exit_of=opened["intent_id"])
        closed = gateway.propose(closing, LATER)
        self.assertTrue(closed["approved"], closed["reasons"])
        self.assertEqual(len(critic.asked), 1)
        self.assertEqual(self.log.read(kind="risk.review", limit=10)[-1].payload["intent_id"], opened["intent_id"])

    def test_the_board_can_ask_for_a_positions_plan_and_its_resting_exits(self):
        self.open_position()
        plan = self.book.plan_for_position(DESK, AAPL.key)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.stop_price, Decimal("95"))
        self.assertEqual(self.book.exit_orders(plan), [])
        self.assertIsNone(self.book.plan_for_position(DESK, BTC.key))


class PublishRowTests(unittest.TestCase):
    def test_positions_live_session_and_the_watch_ride_on_the_checkpoint_when_given(self):
        body = checkpoint_body(
            published_at=NOW,
            floor={"equity": Decimal("1"), "cash": Decimal("1"), "daily_pnl": Decimal("0"),
                   "capital_usd": Decimal("1"), "since_inception_pct": Decimal("0"), "benchmark": None,
                   "live_desks": 1, "shadow_desks": 0},
            desks=[{
                "id": DESK, "name": "Earnings", "family": "earnings", "generation": 1, "parent_id": None,
                "mode": "live", "venues": ["alpaca"], "capital_usd": Decimal("1"), "equity": Decimal("1"),
                "cash": Decimal("1"), "daily_pnl": Decimal("0"), "return_pct": Decimal("0"),
                "max_drawdown_pct": Decimal("0"), "days_live": 1, "orders": 1, "cost_usd": Decimal("0"),
                "status": "active", "gate": None, "updated_at": NOW,
                "positions": [{
                    "instrument": AAPL.to_dict(), "side": "long", "quantity": Decimal("2"),
                    "entry_price": Decimal("100"), "mark_price": Decimal("104"), "market_value": Decimal("208"),
                    "unrealized_pnl": Decimal("8"), "opened_at": NOW, "thesis": "x" * 400,
                    "intent_id": "oi-1", "session_id": "s1", "target_price": Decimal("110"),
                    "stop_price": Decimal("95"), "time_stop_at": LATER,
                    "exit_orders": [{"id": "ord-9", "kind": "stop", "price": Decimal("95")}],
                }],
                "live_session": {"session_id": "s1", "trigger": "cadence:09:45", "started_at": NOW},
            }],
            committee={"last_memo_at": None, "allocations": {}},
            budget={"spent_today_usd": Decimal("0"), "cap_usd": Decimal("1")},
            watch={"triggers_today": 3, "wakes_today": 1, "last_trigger_at": NOW, "cost_today_usd": "0.002"},
        )
        row = body["desks"][0]["positions"][0]
        self.assertEqual(row["instrument"], {"symbol": "AAPL", "asset_class": "equity", "venue": "alpaca"})
        self.assertEqual(len(row["thesis"]), 240)
        self.assertEqual(row["intent_id"], "oi-1")
        self.assertEqual(row["session_id"], "s1")
        self.assertEqual(row["unrealized_pnl"], Decimal("8"))
        self.assertEqual(row["exit_orders"], [{"id": "ord-9", "kind": "stop", "price": Decimal("95")}])
        self.assertEqual(body["desks"][0]["live_session"]["trigger"], "cadence:09:45")
        self.assertEqual(body["watch"], {"triggers_today": 3, "wakes_today": 1, "last_trigger_at": NOW,
                                         "cost_today_usd": Decimal("0.002")})

    def test_an_older_floor_publishes_none_of_it(self):
        body = checkpoint_body(
            published_at=NOW,
            floor={"equity": Decimal("1"), "cash": Decimal("1"), "daily_pnl": Decimal("0"),
                   "capital_usd": Decimal("1"), "since_inception_pct": Decimal("0"), "benchmark": None,
                   "live_desks": 1, "shadow_desks": 0},
            desks=[{"id": DESK, "name": "E", "family": "earnings", "generation": 1, "parent_id": None,
                    "mode": "live", "venues": ["alpaca"], "capital_usd": Decimal("1"), "equity": Decimal("1"),
                    "cash": Decimal("1"), "daily_pnl": Decimal("0"), "return_pct": Decimal("0"),
                    "max_drawdown_pct": Decimal("0"), "days_live": 1, "orders": 1, "cost_usd": Decimal("0"),
                    "status": "active", "gate": None, "updated_at": NOW}],
            committee={"last_memo_at": None, "allocations": {}},
            budget={"spent_today_usd": Decimal("0"), "cap_usd": Decimal("1")},
        )
        self.assertNotIn("positions", body["desks"][0])
        self.assertNotIn("live_session", body["desks"][0])
        self.assertNotIn("watch", body)


class BoardTests(ServiceCase):
    """The floor's checkpoint carries what each desk holds, why, and the plan against it."""

    def broker_factory(self, venue, *, manifest=None, path=None, settings=None, service=None):
        if manifest is None:
            return self.venues.get(venue)
        broker = self.brokers.get(manifest.id)
        if broker is None:
            broker = self.brokers[manifest.id] = ClockedBroker()
        return broker

    def test_the_checkpoint_shows_the_position_its_thesis_and_its_exit_plan(self):
        self.fund()
        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity="2",
            rationale="Revenue beat with guidance raised; " + "detail " * 60,
            created_at=self.service.now(), session_id="s-board",
            target_price="110", stop_price="95", time_stop_at="2026-09-16T13:50:00.000Z",
        )
        result = self.service.gateway.propose(intent, self.service.now())
        self.assertTrue(result["approved"], result["reasons"])
        self.tick()
        checkpoint = self.publisher.checkpoints[-1]
        desk = next(d for d in checkpoint["desks"] if d["id"] == DESK)
        self.assertEqual(len(desk["positions"]), 1)
        row = desk["positions"][0]
        self.assertEqual(row["side"], "long")
        self.assertEqual(str(row["quantity"]), "2")
        self.assertEqual(row["intent_id"], intent.id)
        self.assertEqual(row["session_id"], "s-board")
        self.assertEqual(row["thesis"], intent.rationale[:240])
        self.assertEqual(str(row["target_price"]), "110")
        self.assertEqual(str(row["stop_price"]), "95")
        self.assertEqual(row["time_stop_at"], "2026-09-16T13:50:00.000Z")
        self.assertEqual(row["exit_orders"], [])
        self.assertEqual(str(row["entry_price"]), "100")
        self.assertIn("watch", checkpoint)
        self.assertEqual(checkpoint["watch"]["wakes_today"], 0)
        status = self.service.status()
        self.assertEqual(status["exit_plans"], 1)
        self.assertNotIn("live_session", desk)

    def test_the_floor_closes_a_position_at_its_time_stop_between_sessions(self):
        self.fund()
        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity="2", rationale="a dated thesis",
            created_at=self.service.now(), session_id="s", time_stop_at="2026-09-14T15:00:00.000Z",
        )
        self.assertTrue(self.service.gateway.propose(intent, self.service.now())["approved"])
        self.tick()
        self.assertEqual(self.tick(moment(2026, 9, 14, 14, 0))["exits"], [])
        result = self.tick(moment(2026, 9, 14, 15, 1))
        self.assertEqual([o["reason"] for o in result["exits"]], ["time_stop"])
        self.assertTrue(result["exits"][0]["approved"], result["exits"])
        self.assertEqual(self.service.ledgers[DESK].state(self.service.now()).positions, {})
        exits = [e for e in self.service.log.read(kind="broker.order") if e.payload.get("purpose") == "exit"]
        self.assertEqual(exits[-1].payload["exit_of"], intent.id)



class EventTimeStopTests(unittest.TestCase):
    def test_an_event_contract_is_never_time_stopped(self):
        """It settles; selling it into the spread minutes before the venue pays in full is a loss
        the desk never asked for. The stop and the target still apply."""
        contract = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="yes")
        plan = ExitPlan.from_intent(entry(instrument=contract, target_price="0.90", stop_price="0.20"))
        self.assertIsNone(plan.due(Decimal("0.50"), LATER))
        self.assertIsNone(plan.due(None, LATER))
        self.assertEqual(plan.due(Decimal("0.19"), LATER), "stop")
        self.assertEqual(plan.due(Decimal("0.95"), NOW), "target")
        self.assertEqual(ExitPlan.from_intent(entry()).due(Decimal("100"), LATER), "time_stop", "spot still is")


if __name__ == "__main__":
    unittest.main()

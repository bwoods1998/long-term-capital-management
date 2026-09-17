"""`ShadowBook`: fills, resting limits, expiry, settlement, fees, idempotency and marks.

Everything here runs against a scripted `MarketData` and an injected clock, so the same inputs
always produce the same fills, the same fill ids and the same equity curve.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument, OrderIntent, RejectedOrder
from ltcm.sim import FeeModel, SHADOW_CAPABILITIES, ShadowBook, ceil_cents
from ltcm.tests.fakes import Clock, ScriptedMarketData

OPEN = "2026-09-15T14:00:00Z"  # inside the 13:30-20:00Z session of Tuesday 15 September 2026
CLOSE = "2026-09-15T20:00:00Z"

AAPL = Instrument("equity", "AAPL", "shadow")
BTC = Instrument("crypto", "BTC-USD", "shadow", market_id="BTC-USD")
CALL = Instrument(
    "option", "AAPL", "shadow", multiplier="100", expiry="2026-10-16", strike="200", right="call"
)
CPI = Instrument("event", "CPI", "shadow", market_id="KXCPI-26SEP-T3.0")
CPI_NO = Instrument("event", "CPI", "shadow", market_id="KXCPI-26SEP-T3.0", right="no")


def intent(instrument=AAPL, side="buy", quantity="10", **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", OPEN)
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, side=side, quantity=quantity, **kwargs)


class SimTestCase(unittest.TestCase):
    """One broker on a throwaway SQLite file, a scripted book and a clock the test drives."""

    initial_cash = "100000"
    allow_short = False
    slippage_bps = 5

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.clock = Clock(OPEN)
        self.data = ScriptedMarketData(self.clock)
        self.broker = self.make_broker()
        self.addCleanup(self.broker.close)

    def make_broker(self, name="sim.db", **kwargs):
        options = {
            "venue": "shadow",
            "data": self.data,
            "clock": self.clock,
            "initial_cash": self.initial_cash,
            "slippage_bps": self.slippage_bps,
            "allow_short": self.allow_short,
        }
        options.update(kwargs)
        return ShadowBook(Path(self._directory.name) / name, **options)

    def book(self, instrument=AAPL, *, bid="99", ask="101", last="100"):
        return self.data.set(instrument, bid=bid, ask=ask, last=last)


class CapabilityTests(SimTestCase):
    def test_capabilities_reflect_the_configuration(self):
        caps = self.broker.capabilities()
        self.assertEqual(caps, set(SHADOW_CAPABILITIES))
        self.assertIn("shadow", caps)
        self.assertNotIn("short", caps)
        shorting = self.make_broker("short.db", allow_short=True)
        self.addCleanup(shorting.close)
        self.assertIn("short", shorting.capabilities())

    def test_the_venue_on_the_instrument_is_honoured(self):
        self.book()
        elsewhere = Instrument("equity", "AAPL", "alpaca")
        with self.assertRaises(RejectedOrder):
            self.broker.submit(intent(elsewhere))


class MarketOrderTests(SimTestCase):
    def test_a_market_buy_pays_the_ask_plus_slippage(self):
        self.book(ask="101")
        order = self.broker.submit(intent())
        self.assertEqual(order.status, "filled")
        self.assertEqual(order.filled_quantity, Decimal("10"))
        # 101 * (1 + 5/10000) = 101.0505
        self.assertEqual(order.average_price, Decimal("101.05050000"))
        self.assertEqual(self.broker.cash, Decimal("100000") - Decimal("101.0505") * 10)
        position = self.broker.position(AAPL)
        self.assertEqual(position.quantity, Decimal("10"))
        self.assertEqual(position.average_cost, Decimal("101.05050000"))

    def test_a_market_sell_receives_the_bid_minus_slippage(self):
        self.book()
        self.broker.submit(intent())
        self.clock.advance(60)
        order = self.broker.submit(intent(side="sell", quantity="4", nonce="sell"))
        # 99 * (1 - 5/10000) = 98.9505
        self.assertEqual(order.average_price, Decimal("98.95050000"))
        self.assertEqual(self.broker.position(AAPL).quantity, Decimal("6"))
        # realized = (98.9505 - 101.0505) * 4
        self.assertEqual(self.broker.realized_pnl, Decimal("-8.4"))

    def test_no_quote_is_a_rejection_that_is_recorded(self):
        with self.assertRaises(RejectedOrder):
            self.broker.submit(intent())
        order = self.broker.order_for_intent(intent().id)
        self.assertEqual(order.status, "rejected")
        self.assertIn("no quote", order.reason)
        self.assertEqual(self.broker.cash, Decimal("100000"))
        self.assertEqual(self.broker.positions(), [])

    def test_insufficient_cash_is_a_rejection(self):
        self.book(ask="101")
        with self.assertRaises(RejectedOrder) as caught:
            self.broker.submit(intent(quantity="5000"))
        self.assertIn("insufficient cash", str(caught.exception))
        self.assertEqual(self.broker.cash, Decimal("100000"))

    def test_selling_what_is_not_held_is_a_rejection_without_shorting(self):
        self.book()
        with self.assertRaises(RejectedOrder) as caught:
            self.broker.submit(intent(side="sell"))
        self.assertIn("insufficient position", str(caught.exception))

    def test_shorting_is_allowed_when_configured(self):
        shorting = self.make_broker("short.db", allow_short=True)
        self.addCleanup(shorting.close)
        self.book()
        order = shorting.submit(intent(side="sell"))
        self.assertEqual(order.status, "filled")
        self.assertEqual(shorting.position(AAPL).quantity, Decimal("-10"))

    def test_a_quote_with_only_a_last_price_still_fills(self):
        self.data.set(AAPL, last="100")
        order = self.broker.submit(intent())
        self.assertEqual(order.average_price, Decimal("100.05000000"))


class LimitOrderTests(SimTestCase):
    def test_a_marketable_limit_pays_the_touch_not_the_limit(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="105", time_in_force="gtc")
        )
        self.assertEqual(order.status, "filled")
        self.assertEqual(order.average_price, Decimal("101"), "a taker pays the ask, not its limit")

    def test_a_resting_limit_waits_and_then_fills_at_its_limit(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="99", time_in_force="gtc")
        )
        self.assertEqual(order.status, "accepted")
        self.assertEqual(self.broker.cash, Decimal("100000"), "nothing is paid until it fills")
        self.assertEqual([o.id for o in self.broker.open_orders()], [order.id])

        self.clock.advance(60)
        self.book(bid="97", ask="98.5", last="98")
        changed = self.broker.tick()
        self.assertEqual([o.id for o in changed], [order.id])
        filled = self.broker.get_order(order.id)
        self.assertEqual(filled.status, "filled")
        self.assertEqual(filled.average_price, Decimal("99"))
        self.assertEqual(self.broker.open_orders(), [])

    def test_a_resting_limit_sell_fills_when_the_bid_rises_through_it(self):
        self.book()
        self.broker.submit(intent())
        self.clock.advance(30)
        order = self.broker.submit(
            intent(side="sell", quantity="10", order_type="limit", limit_price="110", time_in_force="gtc")
        )
        self.assertEqual(order.status, "accepted")
        self.clock.advance(30)
        self.book(bid="112", ask="113", last="112.5")
        changed = self.broker.tick()
        self.assertEqual([o.status for o in changed], ["filled"])
        self.assertEqual(self.broker.get_order(order.id).average_price, Decimal("110"))
        self.assertEqual(self.broker.positions(), [])

    def test_ioc_cancels_at_once_when_it_is_not_marketable(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="90", time_in_force="ioc")
        )
        self.assertEqual(order.status, "cancelled")
        self.assertIn("ioc", order.reason)
        self.assertEqual(self.broker.open_orders(), [])

    def test_ioc_fills_immediately_when_it_is_marketable(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="101", time_in_force="ioc")
        )
        self.assertEqual(order.status, "filled")

    def test_a_day_order_expires_at_the_session_close(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="90", time_in_force="day")
        )
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order._raw["expires_at"], CLOSE)

        self.clock.set("2026-09-15T19:59:59Z")
        self.assertEqual(self.broker.tick(), [])
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")

        self.clock.set(CLOSE)
        changed = self.broker.tick()
        self.assertEqual([o.status for o in changed], ["expired"])
        self.assertEqual(self.broker.get_order(order.id).status, "expired")
        self.assertEqual(self.broker.open_orders(), [])

    def test_a_day_order_placed_after_the_close_lives_until_the_next_close(self):
        self.clock.set("2026-09-18T22:00:00Z")  # Friday evening
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="90", time_in_force="day", created_at="after")
        )
        self.assertEqual(order._raw["expires_at"], "2026-09-21T20:00:00Z")  # Monday's close

    def test_a_crypto_day_order_dies_at_the_next_utc_midnight(self):
        self.book(BTC, bid="64000", ask="64100", last="64050")
        order = self.broker.submit(
            intent(BTC, quantity="0.01", order_type="limit", limit_price="60000", time_in_force="day")
        )
        self.assertEqual(order._raw["expires_at"], "2026-09-16T00:00:00Z")

    def test_a_gtc_order_survives_days_of_ticks(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="90", time_in_force="gtc")
        )
        self.assertIsNone(order._raw["expires_at"])
        for day in ("2026-09-16T20:00:00Z", "2026-09-21T20:00:00Z", "2026-10-01T20:00:00Z"):
            self.clock.set(day)
            self.assertEqual(self.broker.tick(), [])
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")

    def test_cancel_is_idempotent_on_a_terminal_order(self):
        self.book(ask="101")
        order = self.broker.submit(
            intent(order_type="limit", limit_price="90", time_in_force="gtc")
        )
        cancelled = self.broker.cancel(order.id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(self.broker.cancel(order.id).status, "cancelled")
        with self.assertRaises(RejectedOrder):
            self.broker.cancel("ord-nope")


class IdempotencyTests(SimTestCase):
    def test_submitting_the_same_intent_twice_creates_one_order_and_one_fill(self):
        self.book(ask="101")
        proposal = intent()
        first = self.broker.submit(proposal)
        self.clock.advance(120)
        second = self.broker.submit(proposal)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.broker.orders()), 1)
        self.assertEqual(len(self.broker.fills()), 1)
        self.assertEqual(self.broker.position(AAPL).quantity, Decimal("10"))
        self.assertEqual(second.average_price, first.average_price)

    def test_a_rejected_intent_stays_rejected_on_resubmission(self):
        proposal = intent()
        with self.assertRaises(RejectedOrder):
            self.broker.submit(proposal)
        self.book(ask="101")
        again = self.broker.submit(proposal)
        self.assertEqual(again.status, "rejected", "the intent id is spent; a new intent is needed")
        self.assertEqual(self.broker.cash, Decimal("100000"))

    def test_the_run_is_deterministic(self):
        self.book(ask="101")
        self.broker.submit(intent())
        first_fills = [f.to_dict() for f in self.broker.fills()]
        first_balance = self.broker.balance().to_dict()

        replay = self.make_broker("replay.db")
        self.addCleanup(replay.close)
        replay.submit(intent())
        self.assertEqual([f.to_dict() for f in replay.fills()], first_fills)
        self.assertEqual(replay.balance().to_dict(), first_balance)


class FractionalTests(SimTestCase):
    def test_crypto_is_fractional(self):
        self.book(BTC, bid="64000", ask="64100", last="64050")
        order = self.broker.submit(intent(BTC, quantity="0.015"))
        self.assertEqual(order.status, "filled")
        self.assertEqual(self.broker.position(BTC).quantity, Decimal("0.015"))

    def test_options_and_event_contracts_are_whole(self):
        self.book(CALL, bid="4.9", ask="5.1", last="5")
        with self.assertRaises(RejectedOrder):
            self.broker.submit(intent(CALL, quantity="1.5"))
        self.book(CPI, bid="0.38", ask="0.41", last="0.40")
        with self.assertRaises(RejectedOrder):
            self.broker.submit(intent(CPI, quantity="2.5"))

    def test_the_option_multiplier_scales_the_notional(self):
        self.book(CALL, bid="4.9", ask="5", last="5")
        order = self.broker.submit(intent(CALL, quantity="2"))
        price = Decimal("5") * Decimal("1.0005")
        fee = Decimal("0.65") * 2
        self.assertEqual(order.average_price, price)
        self.assertEqual(self.broker.cash, Decimal("100000") - price * 2 * 100 - fee)
        self.assertEqual(self.broker.position(CALL).cost_basis, price * 2 * 100)


class FeeTests(unittest.TestCase):
    def setUp(self):
        self.fees = FeeModel.for_venue("alpaca")

    def test_equities_are_free(self):
        self.assertEqual(self.fees.fee(AAPL, "buy", Decimal("100"), Decimal("50")), Decimal("0"))

    def test_options_cost_sixty_five_cents_a_contract(self):
        self.assertEqual(self.fees.fee(CALL, "buy", Decimal("3"), Decimal("5")), Decimal("1.95"))

    def test_crypto_is_twenty_five_basis_points_of_notional(self):
        fee = self.fees.fee(BTC, "buy", Decimal("0.5"), Decimal("64000"))
        self.assertEqual(fee, Decimal("80.00"))  # 0.25% of 32000

    def test_kalshi_uses_the_published_quadratic(self):
        # ceil to the cent of 0.07 * C * P * (1 - P)
        self.assertEqual(self.fees.kalshi_fee(Decimal("10"), Decimal("0.40")), Decimal("0.17"))
        self.assertEqual(self.fees.kalshi_fee(Decimal("1"), Decimal("0.50")), Decimal("0.02"))
        self.assertEqual(self.fees.kalshi_fee(Decimal("100"), Decimal("0.99")), Decimal("0.07"))
        self.assertEqual(self.fees.kalshi_fee(Decimal("10"), Decimal("1")), Decimal("0.00"))
        self.assertEqual(self.fees.fee(CPI, "buy", Decimal("10"), Decimal("0.40")), Decimal("0.17"))

    def test_the_fee_always_rounds_up_to_the_next_cent(self):
        self.assertEqual(ceil_cents(Decimal("0.0001")), Decimal("0.01"))
        self.assertEqual(ceil_cents(Decimal("0.17")), Decimal("0.17"))
        self.assertEqual(ceil_cents(Decimal("0.171")), Decimal("0.18"))

    def test_a_price_outside_the_dollar_is_refused(self):
        with self.assertRaises(ValueError):
            self.fees.kalshi_fee(Decimal("1"), Decimal("1.5"))

    def test_per_venue_defaults(self):
        self.assertEqual(FeeModel.for_venue("coinbase").crypto_maker_pct, Decimal("0.005"))
        self.assertEqual(FeeModel.for_venue("kalshi").event_fee_rate, Decimal("0.07"))
        self.assertEqual(FeeModel.for_venue("unknown").option_per_contract, Decimal("0.65"))
        with self.assertRaises(ValueError):
            FeeModel(option_per_contract=Decimal("-1"))

    def test_fees_are_charged_on_a_simulated_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock(OPEN)
            data = ScriptedMarketData(clock)
            data.set(BTC, bid="64000", ask="64000", last="64000")
            broker = ShadowBook(
                Path(directory) / "fees.db",
                data=data,
                clock=clock,
                initial_cash="100000",
                slippage_bps=0,
            )
            try:
                broker.submit(intent(BTC, quantity="1"))
                fill = broker.fills()[0]
                self.assertEqual(fill.price, Decimal("64000"))
                self.assertEqual(fill.fee, Decimal("160.00"))
                self.assertEqual(broker.cash, Decimal("100000") - Decimal("64160"))
            finally:
                broker.close()


class MakerFeeTests(SimTestCase):
    def test_a_resting_event_order_that_fills_later_pays_no_fee_and_a_taker_pays_the_formula(self):
        # Kalshi charges the taker; every maker fill on Sept 16, 2026 came back with fee 0.
        broker = self.make_broker("kalshi.db", market_venue="kalshi", slippage_bps=0)
        self.addCleanup(broker.close)
        self.book(CPI_NO, bid="0.70", ask="0.74", last="0.72")
        resting = broker.submit(intent(CPI_NO, quantity="10", order_type="limit", limit_price="0.70", time_in_force="gtc"))
        self.assertEqual(resting.status, "accepted", "a bid under the ask rests")
        taker = broker.submit(intent(CPI_NO, quantity="10", order_type="limit", limit_price="0.74", time_in_force="gtc"))
        self.assertEqual(taker.status, "filled")
        taker_fill = [f for f in broker.fills() if f.order_id == taker.id][0]
        self.assertEqual(taker_fill.fee, Decimal("0.14"), "0.07 x 10 x 0.74 x 0.26 rounded up to the cent")
        # The market comes down to the resting bid: it fills at its own price, and pays nothing.
        self.book(CPI_NO, bid="0.66", ask="0.70", last="0.69")
        self.clock.advance(60)
        broker.tick()
        rested_fill = [f for f in broker.fills() if f.order_id == resting.id][0]
        # KXCPI is one of the series that charge makers: ceil(0.0175 x 10 x 0.70 x 0.30) = $0.04.
        # A series that does not (most of the board) charges the resting fill nothing.
        self.assertEqual((rested_fill.price, rested_fill.fee), (Decimal("0.70"), Decimal("0.04")))


class SettlementTests(SimTestCase):
    def setUp(self):
        super().setUp()
        self.book(CPI, bid="0.39", ask="0.40", last="0.40")
        self.broker.submit(
            intent(CPI, quantity="10", order_type="limit", limit_price="0.40", time_in_force="gtc")
        )
        self.entry = self.broker.cash

    def test_a_winning_market_pays_a_dollar_a_contract(self):
        self.assertEqual(self.broker.position(CPI).quantity, Decimal("10"))
        self.clock.advance(3600)
        settled = self.broker.settle_event("KXCPI-26SEP-T3.0", "1")
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0].price, Decimal("1"))
        self.assertEqual(settled[0].quantity, Decimal("10"))
        self.assertEqual(settled[0].side, "sell")
        self.assertEqual(self.broker.cash, self.entry + Decimal("10"))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.realized_pnl, Decimal("6.00") - Decimal("0.17"))

    def test_a_losing_market_pays_nothing_and_closes_the_position(self):
        self.clock.advance(3600)
        settled = self.broker.settle_event("KXCPI-26SEP-T3.0", "0")
        self.assertEqual(settled[0].price, Decimal("0"))
        self.assertEqual(self.broker.cash, self.entry)
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.realized_pnl, Decimal("-4.00") - Decimal("0.17"))

    def test_settlement_cancels_resting_orders_on_that_market(self):
        resting = self.broker.submit(
            intent(CPI, quantity="5", order_type="limit", limit_price="0.10", time_in_force="gtc", nonce="rest")
        )
        self.assertEqual(resting.status, "accepted")
        self.clock.advance(60)
        self.broker.settle_event("KXCPI-26SEP-T3.0", "1")
        self.assertEqual(self.broker.get_order(resting.id).status, "cancelled")
        self.assertEqual(self.broker.open_orders(), [])

    def test_settling_twice_is_a_no_op(self):
        self.clock.advance(60)
        self.broker.settle_event("KXCPI-26SEP-T3.0", "1")
        cash = self.broker.cash
        self.assertEqual(self.broker.settle_event("KXCPI-26SEP-T3.0", "1"), [])
        self.assertEqual(self.broker.cash, cash)

    def test_a_payout_outside_the_dollar_is_refused(self):
        for bad in ("1.01", "-0.5"):
            with self.assertRaises(ValueError):
                self.broker.settle_event("KXCPI-26SEP-T3.0", bad)


class NoLegSettlementTests(SimTestCase):
    """`payout_per_contract` is the yes value; a NO position is paid its complement."""

    def setUp(self):
        super().setUp()
        self.book(CPI_NO, bid="0.59", ask="0.60", last="0.60")
        self.broker.submit(
            intent(CPI_NO, quantity="10", order_type="limit", limit_price="0.60",
                   time_in_force="gtc")
        )
        self.entry = self.broker.cash

    def test_a_no_position_is_paid_a_dollar_when_the_market_resolves_no(self):
        self.clock.advance(3600)
        settled = self.broker.settle_event("KXCPI-26SEP-T3.0", "0")
        self.assertEqual(settled[0].price, Decimal("1"))
        self.assertEqual(settled[0].side, "sell")
        self.assertEqual(self.broker.cash, self.entry + Decimal("10"))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.realized_pnl, Decimal("4.00") - Decimal("0.17"))

    def test_a_no_position_is_paid_nothing_when_the_market_resolves_yes(self):
        self.clock.advance(3600)
        settled = self.broker.settle_event("KXCPI-26SEP-T3.0", "1")
        self.assertEqual(settled[0].price, Decimal("0"))
        self.assertEqual(self.broker.cash, self.entry)
        self.assertEqual(self.broker.realized_pnl, Decimal("-6.00") - Decimal("0.17"))

    def test_both_legs_of_one_market_settle_to_a_dollar_between_them(self):
        self.book(CPI, bid="0.39", ask="0.40", last="0.40")
        self.broker.submit(
            intent(CPI, quantity="10", order_type="limit", limit_price="0.40",
                   time_in_force="gtc", nonce="yes-leg")
        )
        cash = self.broker.cash
        self.clock.advance(3600)
        settled = {f.instrument.right or "yes": f.price for f in
                   self.broker.settle_event("KXCPI-26SEP-T3.0", "1")}
        self.assertEqual(settled, {"yes": Decimal("1"), "no": Decimal("0")})
        # Ten of each leg is ten dollars however the market resolves.
        self.assertEqual(self.broker.cash, cash + Decimal("10"))
        self.assertEqual(self.broker.positions(), [])


class MarkTests(SimTestCase):
    def test_mark_revalues_positions_and_records_an_equity_point(self):
        self.book(ask="100", bid="100", last="100")
        self.broker.submit(intent(quantity="10"))
        paid = Decimal("100") * Decimal("1.0005") * 10

        self.clock.advance(3600)
        self.book(bid="109", ask="111", last="110")
        balance = self.broker.mark()
        self.assertEqual(self.broker.position(AAPL).mark, Decimal("110"))
        self.assertEqual(balance.equity, Decimal("100000") - paid + Decimal("1100"))
        self.assertEqual(balance.as_of, self.clock.iso)

        marks = self.broker.marks()
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["at"], self.clock.iso)
        self.assertEqual(Decimal(marks[0]["equity"]), balance.equity)
        self.assertEqual(len(marks[0]["positions"]), 1)

    def test_mark_accepts_an_explicit_moment(self):
        self.book()
        self.broker.submit(intent())
        balance = self.broker.mark("2026-09-16T20:00:00Z")
        self.assertEqual(balance.as_of, "2026-09-16T20:00:00Z")
        self.assertEqual(self.broker.marks()[0]["at"], "2026-09-16T20:00:00Z")

    def test_an_unquotable_position_keeps_its_last_known_mark(self):
        self.book()
        self.broker.submit(intent())
        self.clock.advance(60)
        self.broker.mark()
        self.data.clear(AAPL)
        self.clock.advance(60)
        balance = self.broker.mark()
        self.assertEqual(self.broker.position(AAPL).mark, Decimal("100"))
        self.assertIsNotNone(balance.equity)

    def test_snapshot_carries_what_the_ledger_stream_needs(self):
        self.book()
        self.broker.submit(intent())
        self.broker.mark()
        snapshot = self.broker.snapshot()
        self.assertEqual(snapshot["venue"], "shadow")
        self.assertEqual(Decimal(snapshot["initial_cash"]), Decimal("100000"))
        self.assertEqual(len(snapshot["positions"]), 1)
        self.assertIn("fees_paid", snapshot)

    def test_deposits_move_cash_and_the_capital_base(self):
        self.broker.deposit("5000")
        self.assertEqual(self.broker.cash, Decimal("105000"))
        self.assertEqual(Decimal(self.broker.snapshot()["initial_cash"]), Decimal("105000"))
        with self.assertRaises(ValueError):
            self.broker.deposit("-1000000")


class FillHistoryTests(SimTestCase):
    def test_fills_since_is_inclusive_of_the_stamp(self):
        self.book()
        self.broker.submit(intent(quantity="1"))
        first = self.broker.fills()[0]
        self.clock.advance(60)
        self.broker.submit(intent(quantity="2", nonce="2"))
        self.clock.advance(60)
        self.broker.submit(intent(quantity="3", nonce="3"))

        self.assertEqual(len(self.broker.fills()), 3)
        # The cursor is inclusive: two fills in one second must both be returned, and the
        # gateway dedupes by fill id.
        later = self.broker.fills(since=first.at)
        self.assertEqual(len(later), 3)
        self.assertTrue(all(fill.at >= first.at for fill in later))
        self.assertEqual(len(self.broker.fills(since=later[-1].at)), 1)

    def test_a_fill_round_trips_through_its_dict(self):
        self.book()
        self.broker.submit(intent())
        fill = self.broker.fills()[0]
        payload = fill.to_dict()
        self.assertEqual(payload["desk_id"], "desk-1")
        self.assertEqual(payload["side"], "buy")
        self.assertTrue(fill.id.startswith("fl-"))

    def test_persisted_state_survives_reopening_the_file(self):
        self.book()
        self.broker.submit(intent())
        cash = self.broker.cash
        self.broker.close()
        reopened = self.make_broker("sim.db")
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.cash, cash)
        self.assertEqual(reopened.position(AAPL).quantity, Decimal("10"))
        self.assertEqual(len(reopened.fills()), 1)


if __name__ == "__main__":
    unittest.main()


class TakerModelTests(SimTestCase):
    """leap: taker model -- prints fill the resting quotes a taker would have hit."""

    NO = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="no")
    BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")

    def test_a_print_on_the_other_leg_fills_a_resting_no_bid_at_its_own_limit_in_pieces(self):
        self.book(self.NO, bid="0.68", ask="0.70", last="0.69")
        self.broker = self.make_broker("kalshi.db", market_venue="kalshi")
        self.addCleanup(self.broker.close)
        order = self.broker.submit(intent(self.NO, quantity="10", order_type="limit", limit_price="0.65"))
        self.assertEqual(order.status, "accepted", "0.65 rests under the 0.70 ask")
        self.assertEqual(self.broker.on_trade("kalshi", "KXBTC-1", "0.36", "5", "no"), [], "a taker buying NO lifts the ask; our bid is not hit")
        self.assertEqual(self.broker.on_trade("kalshi", "KXBTC-1", "0.30", "5", "yes"), [], "YES bought at 0.30 is NO sold at 0.70, above our 0.65 bid: not hit")
        changed = self.broker.on_trade("kalshi", "KXBTC-1", "0.37", "4", "yes")  # NO sold at 0.63 <= 0.65
        self.assertEqual([(o.status, o.filled_quantity, o.average_price) for o in changed], [("partially_filled", Decimal("4"), Decimal("0.65"))])
        changed = self.broker.on_trade("kalshi", "KXBTC-1", "0.35", "50", "yes")
        self.assertEqual([(o.status, o.filled_quantity) for o in changed], [("filled", Decimal("10"))])
        position = self.broker.position(self.NO)
        self.assertEqual((position.quantity, position.average_cost), (Decimal("10"), Decimal("0.65")))
        fills = self.broker.fills()
        self.assertEqual(sorted(f.quantity for f in fills), [Decimal("4"), Decimal("6")])

    def test_two_prints_of_the_same_size_in_the_same_second_are_two_fills(self):
        self.book(self.BTC, bid="100", ask="101", last="100.5")
        self.broker = self.make_broker("coinbase.db", market_venue="coinbase")
        self.addCleanup(self.broker.close)
        bid = self.broker.submit(intent(self.BTC, quantity="1", order_type="limit", limit_price="99"))
        self.assertEqual(bid.status, "accepted")
        at = "2026-09-16T13:21:53Z"
        self.broker.on_trade("coinbase", "BTC-USD", "98.5", "0.25", "sell", now=at)
        self.broker.on_trade("coinbase", "BTC-USD", "98.5", "0.25", "sell", now=at)
        self.broker.on_trade("coinbase", "BTC-USD", "98.5", "0.5", "sell", now=at)
        self.assertEqual(self.broker.get_order(bid.id).status, "filled")
        fills = [f for f in self.broker.fills() if f.order_id == bid.id]
        self.assertEqual(sorted(f.quantity for f in fills), [Decimal("0.25"), Decimal("0.25"), Decimal("0.5")])
        self.assertEqual(sum(f.quantity for f in fills), self.broker.position(self.BTC).quantity, "the fills the ledger folds equal the book's position")

    def test_a_crypto_print_by_a_selling_taker_fills_a_resting_bid_and_a_buying_taker_a_resting_offer(self):
        self.book(self.BTC, bid="100", ask="101", last="100.5")
        self.broker = self.make_broker("coinbase.db", market_venue="coinbase")
        self.addCleanup(self.broker.close)
        bid = self.broker.submit(intent(self.BTC, quantity="1", order_type="limit", limit_price="99"))
        self.assertEqual(bid.status, "accepted")
        self.assertEqual(self.broker.on_trade("coinbase", "BTC-USD", "98.5", "2", "buy"), [], "a buying taker does not hit a bid")
        filled = self.broker.on_trade("coinbase", "BTC-USD", "98.5", "2", "sell")
        self.assertEqual([(o.status, o.average_price) for o in filled], [("filled", Decimal("99"))])
        offer = self.broker.submit(intent(self.BTC, side="sell", quantity="1", order_type="limit", limit_price="103"))
        self.assertEqual(offer.status, "accepted")
        self.assertEqual(self.broker.on_trade("coinbase", "ETH-USD", "104", "1", "buy"), [], "another product")
        self.assertEqual([o.status for o in self.broker.on_trade("coinbase", "BTC-USD", "103.5", "1", "buy")], ["filled"])


class KalshiSeriesFeeTests(unittest.TestCase):
    """Sept 17, 2026: 160 Kalshi series charge makers, and some scale every fee."""

    def test_a_maker_fee_series_charges_the_resting_fill(self):
        fees = FeeModel.for_venue("kalshi")
        game = Instrument("event", "KXNHLGAME-26OCT01BOSNYR-BOS", "kalshi", market_id="KXNHLGAME-26OCT01BOSNYR-BOS", right="yes")
        weather = Instrument("event", "KXHIGHNY-26SEP17-B77.5", "kalshi", market_id="KXHIGHNY-26SEP17-B77.5", right="no")
        # ceil(0.0175 x 100 x 0.5 x 0.5) = ceil(0.4375) cents -> $0.44
        self.assertEqual(fees.fee(game, "buy", Decimal("100"), Decimal("0.5"), liquidity="maker"), Decimal("0.44"))
        self.assertEqual(fees.fee(weather, "buy", Decimal("100"), Decimal("0.5"), liquidity="maker"), Decimal("0"))
        self.assertEqual(fees.fee(weather, "buy", Decimal("100"), Decimal("0.5"), liquidity="taker"), Decimal("1.75"))

    def test_a_series_multiplier_scales_the_fee(self):
        schedule = {"KXHALF": {"maker": False, "multiplier": 0.5}}
        fees = FeeModel(event_fee_rate=Decimal("0.07"), kalshi_series=schedule)
        half = Instrument("event", "KXHALF-26SEP17-X", "kalshi", market_id="KXHALF-26SEP17-X", right="yes")
        self.assertEqual(fees.fee(half, "buy", Decimal("100"), Decimal("0.5"), liquidity="taker"), Decimal("0.88"))

    def test_coinbase_fees_are_what_the_account_paid(self):
        fees = FeeModel.for_venue("coinbase")
        btc = Instrument("crypto", "BTC-USD", "coinbase")
        self.assertEqual(fees.fee(btc, "buy", Decimal("0.001"), Decimal("25000"), liquidity="maker"), Decimal("0.13"))
        self.assertEqual(fees.fee(btc, "buy", Decimal("0.001"), Decimal("25000"), liquidity="taker"), Decimal("0.30"))

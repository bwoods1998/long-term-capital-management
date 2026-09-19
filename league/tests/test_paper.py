import json
import os
import stat
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ltcm.broker import Broker, BrokerError, Instrument, OrderIntent, Quote, RejectedOrder, VenueUnavailable
from ltcm.data.kalshi import KalshiMarketData

from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import Ledger
from league.paper import KalshiShadowBroker
from league.tests.fakes import Clock, iso

D = Decimal
VENUE = "kalshi-shadow"
BTC = "KXBTCD-26SEP2017-T80999"
ETH = "KXETHD-26SEP2017-T3999"
FED = "KXFED-26OCT-T4.00"  # a series that charges makers (ltcm/data/kalshi_fees.json)


def event(leg="yes", ticker=BTC, venue=VENUE):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


class ScriptedMarketData:
    """Market data by script: a YES bid/ask per ticker (the NO leg is its complement, as the real
    source quotes it) and a market row per ticker (active and unresolved until a test says so)."""

    def __init__(self, clock):
        self.clock = clock
        self.yes = {}
        self.rows = {}
        self.down = False
        self.quote_calls = 0

    def set(self, ticker, bid, ask):
        self.yes[ticker] = (None if bid is None else D(bid), None if ask is None else D(ask))

    def quote(self, instrument):
        self.quote_calls += 1
        if self.down:
            raise RuntimeError("the source is down")
        bid, ask = self.yes[instrument.market_id]
        if instrument.right == "no":
            bid, ask = (None if ask is None else 1 - ask), (None if bid is None else 1 - bid)
        return Quote(instrument, bid, ask, None, iso(self.clock), "scripted", delayed=False)

    def market(self, ticker):
        if self.down:
            raise RuntimeError("the source is down")
        row = {"ticker": ticker, "status": "active", "result": None, "close_time": "2027-01-01T00:00:00Z", "price_ranges": []}
        row.update(self.rows.get(ticker, {}))
        return row


class ShadowCase(unittest.TestCase):
    cash = "1000"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "state" / "kalshi-shadow.json"
        self.clock = Clock()
        self.data = ScriptedMarketData(self.clock)
        self.data.set(BTC, "0.60", "0.62")
        self.broker = self.new_broker()
        self.n = 0

    def tearDown(self):
        self.dir.cleanup()

    def new_broker(self, **kw):
        return KalshiShadowBroker(self.path, self.data, starting_cash=kw.pop("starting_cash", self.cash), clock=self.clock, **kw)

    def intent(self, side, quantity, instrument=None, **kw):
        self.n += 1
        kw.setdefault("order_type", "limit" if "limit_price" in kw else "market")
        return OrderIntent.new(
            desk_id="book-kalshi-shadow", instrument=instrument or event(), side=side, quantity=quantity,
            time_in_force=kw.pop("time_in_force", "gtc"), rationale="test", created_at=iso(self.clock),
            nonce=kw.pop("nonce", str(self.n)), **kw,
        )

    def buy(self, quantity, **kw):
        return self.broker.submit(self.intent("buy", quantity, **kw))

    def sell(self, quantity, **kw):
        return self.broker.submit(self.intent("sell", quantity, **kw))

    def cash_now(self):
        return self.broker.balance().cash

    def held(self):
        return {p.instrument.key: p.quantity for p in self.broker.positions()}


class SurfaceTest(ShadowCase):
    def test_it_is_a_broker_that_says_it_is_a_shadow(self):
        self.assertIsInstance(self.broker, Broker)
        self.assertEqual(self.broker.venue, VENUE)
        self.assertEqual(self.broker.capabilities(), {"event", "limit", "gtc", "ioc", "no_leg", "shadow"})

    def test_a_new_account_is_its_starting_cash(self):
        balance = self.broker.balance()
        self.assertEqual((balance.venue, balance.cash, balance.equity, balance.buying_power), (VENUE, D(1000), D(1000), D(1000)))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.open_orders(), [])
        self.assertEqual(self.broker.fills(), [])
        self.assertEqual(self.broker.settlements(), [])

    def test_quote_is_the_legs_own_and_a_dead_source_is_a_broker_error(self):
        yes, no = self.broker.quote(event("yes")), self.broker.quote(event("no"))
        self.assertEqual((yes.bid, yes.ask), (D("0.60"), D("0.62")))
        self.assertEqual((no.bid, no.ask), (D("0.38"), D("0.40")))
        self.assertEqual(no.instrument, event("no"))
        self.data.down = True
        with self.assertRaises(VenueUnavailable):
            self.broker.quote(event())

    def test_what_the_real_adapter_refuses_is_refused_and_leaves_no_order(self):
        bad = [
            self.intent("buy", "5", instrument=Instrument("crypto", "BTC-USD", VENUE)),
            self.intent("buy", "5", instrument=event(venue="kalshi")),
            self.intent("buy", "1.5"),
            self.intent("buy", "5", instrument=Instrument("event", BTC, VENUE, market_id=BTC, right="maybe")),
            self.intent("buy", "5", limit_price="1.00"),
            self.intent("buy", "5", limit_price="0.615"),  # a whole-cent market
            self.intent("buy", "5", instrument=event("no"), limit_price="0.385"),
        ]
        for intent in bad:
            with self.assertRaises(RejectedOrder, msg=intent.instrument.key):
                self.broker.submit(intent)
        self.assertEqual(self.cash_now(), D(1000))
        self.assertEqual(self.buy("1").broker_order_id, "shadow-1")  # no number was spent on them

    def test_a_market_with_a_finer_grid_takes_a_finer_price(self):
        self.data.rows[BTC] = {"price_ranges": [{"start": "0.0010", "end": "0.9990", "step": "0.0010"}]}
        self.assertEqual(self.buy("5", limit_price="0.595").status, "accepted")


class TakerTest(ShadowCase):
    def test_a_market_buy_fills_at_the_ask_as_a_taker(self):
        order = self.buy("10")
        fee = D("0.1650")  # 0.07 x 10 x 0.62 x 0.38 = 0.16492, rounded up to $0.0001
        self.assertEqual(order.id, "ord-" + order.intent_id[3:])
        self.assertEqual((order.status, order.filled_quantity, order.average_price, order.fees), ("filled", D(10), D("0.62"), fee))
        self.assertEqual(order.fees, Fees("kalshi").charge(event(), "buy", D(10), D("0.62")).usd)
        self.assertEqual(self.cash_now(), D(1000) - D("6.20") - fee)
        position = self.broker.positions()[0]
        self.assertEqual((position.instrument.key, position.quantity, position.average_cost), (event().key, D(10), D("0.62")))
        balance = self.broker.balance()
        self.assertEqual(balance.equity, balance.cash + D("6.20"))  # positions at cost: the fee is spent
        self.assertEqual(balance.buying_power, balance.cash)
        fill = self.broker.fills()[0]
        self.assertEqual((fill.order_id, fill.side, fill.quantity, fill.price, fill.fee), (order.id, "buy", D(10), D("0.62"), fee))

    def test_a_market_sell_fills_at_the_bid_and_the_fee_comes_out_of_the_proceeds(self):
        self.buy("10")
        before = self.cash_now()
        order = self.sell("10")
        fee = Fees("kalshi").charge(event(), "sell", D(10), D("0.60")).usd
        self.assertEqual((order.status, order.average_price, order.fees), ("filled", D("0.60"), fee))
        self.assertGreater(fee, 0)
        self.assertEqual(self.cash_now(), before + D("6.00") - fee)
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.balance().equity, self.cash_now())

    def test_a_partial_sale_keeps_the_rest_at_its_cost(self):
        self.buy("10")
        self.sell("4")
        position = self.broker.positions()[0]
        self.assertEqual((position.quantity, position.average_cost), (D(6), D("0.62")))

    def test_a_market_order_needs_both_sides_of_the_quote(self):
        for bid, ask in ((None, "0.62"), ("0.60", None), ("0", "0.62")):
            self.data.set(BTC, bid, ask)
            order = self.buy("5")
            self.assertEqual(order.status, "rejected")
            self.assertIn("two-sided", order.reason)
        self.data.down = True
        self.assertEqual(self.buy("5").status, "rejected")
        self.assertEqual(self.cash_now(), D(1000))
        self.assertEqual(self.broker.positions(), [])

    def test_a_limit_through_the_touch_fills_at_the_touch_not_at_its_limit(self):
        order = self.buy("10", limit_price="0.65")
        self.assertEqual((order.status, order.average_price), ("filled", D("0.62")))
        self.assertEqual(order.fees, D("0.1650"))  # it took, so it pays the taker fee
        at_the_ask = self.buy("10", limit_price="0.62")
        self.assertEqual((at_the_ask.status, at_the_ask.average_price), ("filled", D("0.62")))
        out = self.sell("10", limit_price="0.55")
        self.assertEqual((out.status, out.average_price), ("filled", D("0.60")))

    def test_a_post_only_order_that_would_cross_is_rejected(self):
        order = self.buy("10", limit_price="0.62", post_only=True)
        self.assertEqual((order.status, order.reason), ("rejected", "post-only order would cross"))
        self.assertEqual(order.filled_quantity, D(0))
        self.assertEqual(self.cash_now(), D(1000))
        self.buy("10")
        ask = self.sell("10", limit_price="0.60", post_only=True)
        self.assertEqual((ask.status, ask.reason), ("rejected", "post-only order would cross"))

    def test_an_ioc_limit_that_does_not_cross_is_cancelled_not_rested(self):
        order = self.buy("10", limit_price="0.61", time_in_force="ioc")
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.broker.open_orders(), [])


class MakerTest(ShadowCase):
    def test_a_resting_buy_fills_only_when_the_ask_trades_through_it(self):
        order = self.buy("10", limit_price="0.60", post_only=True)
        self.assertEqual((order.status, order.filled_quantity, order.broker_order_id), ("accepted", D(0), "shadow-1"))
        self.assertEqual([o.id for o in self.broker.open_orders()], [order.id])
        self.assertEqual(self.broker.advance(), 0)
        self.data.set(BTC, "0.58", "0.60")  # the ask touches the bid's price: the queue ahead fills first
        self.assertEqual(self.broker.advance(), 0)
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")
        self.assertEqual(self.cash_now(), D(1000))
        self.data.set(BTC, "0.57", "0.59")  # through it
        self.assertEqual(self.broker.advance(), 1)
        filled = self.broker.get_order(order.id)
        self.assertEqual((filled.status, filled.filled_quantity, filled.average_price, filled.fees), ("filled", D(10), D("0.60"), D(0)))
        self.assertEqual(self.cash_now(), D(1000) - D("6.00"))  # its own price, and a maker pays nothing here
        self.assertEqual(self.held(), {event().key: D(10)})
        self.assertEqual(self.broker.fills()[0].fee, D(0))
        self.assertEqual(self.broker.advance(), 0)
        self.assertEqual(self.broker.open_orders(), [])

    def test_a_resting_sell_fills_only_when_the_bid_trades_through_it(self):
        self.buy("10")
        before = self.cash_now()
        order = self.sell("10", limit_price="0.64")
        self.assertEqual(order.status, "accepted")
        self.data.set(BTC, "0.64", "0.66")
        self.assertEqual(self.broker.advance(), 0)
        self.data.set(BTC, "0.65", "0.67")
        self.assertEqual(self.broker.advance(), 1)
        filled = self.broker.get_order(order.broker_order_id)
        self.assertEqual((filled.status, filled.average_price, filled.fees), ("filled", D("0.64"), D(0)))
        self.assertEqual(self.cash_now(), before + D("6.40"))
        self.assertEqual(self.broker.positions(), [])

    def test_a_series_that_charges_makers_charges_the_resting_fill(self):
        self.data.set(FED, "0.30", "0.32")
        order = self.buy("20", instrument=event(ticker=FED), limit_price="0.30")
        self.data.set(FED, "0.27", "0.29")
        self.assertEqual(self.broker.advance(), 1)
        fee = D("0.0735")  # 0.0175 x 20 x 0.30 x 0.70
        self.assertEqual(self.broker.get_order(order.id).fees, fee)
        self.assertEqual(self.cash_now(), D(1000) - D("6.00") - fee)

    def test_a_one_sided_book_rests_an_order_and_never_fills_it(self):
        self.data.set(BTC, "0.60", None)
        order = self.buy("10", limit_price="0.61")
        self.assertEqual(order.status, "accepted")
        self.assertEqual(self.broker.advance(), 0)

    def test_a_source_that_cannot_answer_changes_nothing(self):
        order = self.buy("10", limit_price="0.60")
        self.data.set(BTC, "0.50", "0.52")
        self.data.down = True
        self.assertEqual(self.broker.advance(), 0)
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")
        self.data.down = False
        self.assertEqual(self.broker.advance(), 1)

    def test_every_instrument_is_quoted_once_an_advance(self):
        for _ in range(3):
            self.buy("1", limit_price="0.60")
        self.data.quote_calls = 0
        self.broker.advance()
        self.assertEqual(self.data.quote_calls, 1)


class LegTest(ShadowCase):
    def test_the_no_leg_is_bought_at_its_own_ask_and_held_as_its_own_position(self):
        order = self.buy("10", instrument=event("no"))
        self.assertEqual((order.status, order.average_price), ("filled", D("0.40")))  # 1 - the YES bid
        self.assertEqual(order.fees, Fees("kalshi").charge(event("no"), "buy", D(10), D("0.40")).usd)
        self.assertEqual(self.held(), {event("no").key: D(10)})
        self.assertEqual(self.broker.positions()[0].instrument.right, "no")
        refused = self.sell("10", instrument=event("yes"))  # holding NO is not holding YES
        self.assertEqual(refused.status, "rejected")
        out = self.sell("10", instrument=event("no"))
        self.assertEqual((out.status, out.average_price), ("filled", D("0.38")))

    def test_a_resting_no_bid_fills_when_the_no_ask_trades_through_it(self):
        order = self.buy("10", instrument=event("no"), limit_price="0.38", post_only=True)
        self.assertEqual(order.status, "accepted")
        self.data.set(BTC, "0.62", "0.64")  # NO is 0.36 / 0.38: touched
        self.assertEqual(self.broker.advance(), 0)
        self.data.set(BTC, "0.63", "0.65")  # NO is 0.35 / 0.37: through
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.broker.get_order(order.id).average_price, D("0.38"))
        self.assertEqual(self.held(), {event("no").key: D(10)})

    def test_an_unstated_leg_is_the_yes_leg(self):
        bare = Instrument("event", BTC, VENUE, market_id=BTC)
        self.buy("5", instrument=bare)
        self.buy("5", instrument=event("yes"))
        self.assertEqual(self.held(), {event("yes").key: D(10)})


class BackstopTest(ShadowCase):
    cash = "10"

    def test_no_leverage(self):
        order = self.buy("20")  # $12.40 and the fee
        self.assertEqual(order.status, "rejected")
        self.assertIn("insufficient cash", order.reason)
        self.assertEqual(self.cash_now(), D(10))
        exact = self.buy("16")  # $9.92 and a fee of $0.2639: over by the fee
        self.assertEqual(exact.status, "rejected")
        self.assertEqual(self.buy("15").status, "filled")

    def test_resting_buys_hold_their_cash(self):
        self.assertEqual(self.buy("10", limit_price="0.60").status, "accepted")
        second = self.buy("10", limit_price="0.60")
        self.assertEqual(second.status, "rejected")
        self.assertIn("insufficient cash", second.reason)
        self.assertEqual(self.buy("6", limit_price="0.60").status, "accepted")

    def test_no_shorts(self):
        naked = self.sell("5")
        self.assertEqual(naked.status, "rejected")
        self.assertIn("no position to sell", naked.reason)
        self.assertEqual(self.sell("5", limit_price="0.70").status, "rejected")
        self.buy("5")
        self.assertEqual(self.sell("6").status, "rejected")
        self.assertEqual(self.sell("3", limit_price="0.70").status, "accepted")
        self.assertEqual(self.sell("3").status, "rejected")  # three of the five are promised to the resting sell
        self.assertEqual(self.sell("2").status, "filled")


class ExpiryTest(ShadowCase):
    def test_an_order_past_its_expiry_expires_even_if_the_market_traded_through_it_since(self):
        order = self.buy("10", limit_price="0.60", expires_at=iso(Clock(self.clock.now + 600)))
        self.clock.advance(599)
        self.assertEqual(self.broker.advance(), 0)
        self.clock.advance(2)
        self.data.set(BTC, "0.50", "0.52")
        self.assertEqual(self.broker.advance(), 1)
        expired = self.broker.get_order(order.id)
        self.assertEqual((expired.status, expired.filled_quantity), ("expired", D(0)))
        self.assertTrue(expired.terminal)
        self.assertEqual(self.cash_now(), D(1000))

    def test_an_order_on_a_market_that_stopped_trading_expires(self):
        first = self.buy("10", limit_price="0.60")
        self.data.rows[BTC] = {"status": "closed"}
        self.data.set(BTC, "0.50", "0.52")
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.broker.get_order(first.id).status, "expired")
        self.assertEqual(self.cash_now(), D(1000))
        late = self.buy("10")
        self.assertEqual((late.status, late.reason), ("rejected", "the market is closed"))

    def test_a_close_time_in_the_past_is_a_closed_market_whatever_the_status_says(self):
        order = self.buy("10", limit_price="0.60")
        self.data.rows[BTC] = {"status": "active", "close_time": iso(Clock(self.clock.now + 60))}
        self.assertEqual(self.broker.advance(), 0)
        self.clock.advance(61)
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.broker.get_order(order.id).status, "expired")


class OrderBookkeepingTest(ShadowCase):
    def test_the_same_intent_twice_is_one_order(self):
        intent = self.intent("buy", "10")
        first = self.broker.submit(intent)
        self.data.set(BTC, "0.70", "0.72")
        again = self.broker.submit(intent)
        self.assertEqual((again.id, again.broker_order_id, again.average_price), (first.id, "shadow-1", D("0.62")))
        self.assertEqual(len(self.broker.fills()), 1)
        self.assertEqual(self.held(), {event().key: D(10)})
        self.assertEqual(self.buy("1").broker_order_id, "shadow-2")

    def test_a_rejected_intent_stays_rejected(self):
        intent = self.intent("sell", "5")
        self.assertEqual(self.broker.submit(intent).status, "rejected")
        self.buy("5")
        self.assertEqual(self.broker.submit(intent).status, "rejected")

    def test_get_and_cancel(self):
        resting = self.buy("10", limit_price="0.60")
        self.assertEqual(self.broker.get_order(resting.id).broker_order_id, resting.broker_order_id)
        self.assertEqual(self.broker.get_order(resting.broker_order_id).id, resting.id)
        with self.assertRaises(RejectedOrder):
            self.broker.get_order("ord-nothing")
        with self.assertRaises(RejectedOrder):
            self.broker.cancel("shadow-99")
        cancelled = self.broker.cancel(resting.broker_order_id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(self.broker.open_orders(), [])
        self.data.set(BTC, "0.50", "0.52")
        self.assertEqual(self.broker.advance(), 0)  # a cancelled order never fills
        filled = self.buy("10")
        self.assertEqual(self.broker.cancel(filled.id).status, "filled")  # terminal: unchanged

    def test_a_returned_order_is_a_copy(self):
        order = self.buy("10", limit_price="0.60")
        order.status = "filled"
        order.filled_quantity = D(10)
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")

    def test_fills_since(self):
        self.buy("1")
        self.clock.advance(60)
        cut = iso(self.clock)
        self.buy("2")
        self.assertEqual([f.quantity for f in self.broker.fills()], [D(1), D(2)])
        self.assertEqual([f.quantity for f in self.broker.fills(cut)], [D(2)])

    def test_threads_never_share_an_order_number_or_a_dollar(self):
        intents = [self.intent("buy", "1") for _ in range(24)]
        threads = [threading.Thread(target=self.broker.submit, args=(intent,)) for intent in intents]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        orders = [self.broker.get_order("ord-" + intent.id[3:]) for intent in intents]
        self.assertEqual(sorted(int(o.broker_order_id.split("-")[1]) for o in orders), list(range(1, 25)))
        fee = Fees("kalshi").charge(event(), "buy", D(1), D("0.62")).usd
        self.assertEqual(self.cash_now(), D(1000) - 24 * (D("0.62") + fee))
        self.assertEqual(self.held(), {event().key: D(24)})


class SettlementTest(ShadowCase):
    def test_the_winning_leg_is_paid_once_and_the_row_can_be_read_again(self):
        self.data.set(ETH, "0.30", "0.32")
        self.buy("10")  # YES on BTC
        self.buy("4", instrument=event("no"))  # NO on BTC
        self.buy("5", instrument=event("no", ETH))
        resting = self.buy("3", limit_price="0.55")
        self.assertEqual(self.broker.settlements(), [])  # nothing has resolved
        before = self.cash_now()
        start = iso(self.clock)
        self.clock.advance(3600)
        self.data.rows[BTC] = {"status": "finalized", "result": "yes"}
        rows = self.broker.settlements()
        self.assertEqual(
            rows,
            [{"ticker": BTC, "result": "yes", "yes_count": D(10), "no_count": D(4), "revenue": D(10), "settled_time": iso(self.clock)}],
        )
        self.assertEqual(self.cash_now(), before + D(10))
        self.assertEqual(self.held(), {event("no", ETH).key: D(5)})
        self.assertEqual(self.broker.get_order(resting.id).status, "expired")
        # Asked again: paid once, told again.
        self.assertEqual(self.broker.settlements(), rows)
        self.assertEqual(self.broker.settlements(since=start), rows)
        self.assertEqual(self.cash_now(), before + D(10))
        self.clock.advance(3600)
        self.assertEqual(self.broker.settlements(since=iso(self.clock)), [])
        # The other market resolves against the NO leg: it pays nothing and the position goes.
        self.data.rows[ETH] = {"status": "determined", "result": "yes"}
        both = self.broker.settlements()
        self.assertEqual([(r["ticker"], r["revenue"], r["no_count"]) for r in both], [(BTC, D(10), D(4)), (ETH, D(0), D(5))])
        self.assertEqual(self.broker.settlements(since=iso(self.clock)), both[1:])
        self.assertEqual(self.cash_now(), before + D(10))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.balance().equity, self.cash_now())

    def test_a_result_that_is_not_yes_or_no_settles_nothing(self):
        self.buy("10")
        self.data.rows[BTC] = {"status": "closed", "result": ""}
        self.assertEqual(self.broker.settlements(), [])
        self.data.rows[BTC] = {"status": "finalized", "result": "void"}
        self.assertEqual(self.broker.settlements(), [])
        self.assertEqual(self.held(), {event().key: D(10)})

    def test_a_cursor_that_is_not_a_time_is_an_error_not_an_empty_answer(self):
        with self.assertRaises(ValueError):
            self.broker.settlements(since="yesterday")


class RestartTest(ShadowCase):
    def test_a_restart_loses_nothing_and_goes_on_counting(self):
        self.data.set(ETH, "0.30", "0.32")
        self.buy("10")
        self.buy("5", instrument=event("no", ETH))
        resting = self.buy("10", limit_price="0.58", post_only=True, expires_at=iso(Clock(self.clock.now + 3600)))
        self.data.rows[ETH] = {"status": "finalized", "result": "no"}
        settled = self.broker.settlements()
        self.assertEqual(settled[0]["revenue"], D(5))
        old = self.broker
        self.broker = self.new_broker(starting_cash="5")  # only a new account reads starting_cash
        self.assertEqual(self.broker.balance().cash, old.balance().cash)
        self.assertEqual(self.broker.balance().equity, old.balance().equity)
        self.assertEqual(self.held(), {event().key: D(10)})
        self.assertEqual(self.broker.positions()[0].average_cost, D("0.62"))
        self.assertEqual([o.to_dict() for o in self.broker.open_orders()], [o.to_dict() for o in old.open_orders()])
        self.assertEqual(self.broker.get_order(resting.broker_order_id).to_dict(), resting.to_dict())
        self.assertEqual([f.to_dict() for f in self.broker.fills()], [f.to_dict() for f in old.fills()])
        self.assertEqual(self.broker.settlements(), settled)  # known, and not paid again
        self.assertEqual(self.broker.balance().cash, old.balance().cash)
        # The resting order is still working, with its post-only flag and its expiry.
        self.data.set(BTC, "0.55", "0.57")
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.broker.get_order(resting.id).status, "filled")
        self.assertEqual(self.buy("1").broker_order_id, "shadow-4")
        self.assertEqual([f.id for f in self.broker.fills()], ["shadow-fill-1", "shadow-fill-2", "shadow-fill-3", "shadow-fill-4"])
        # And an intent the old process sent is still the same order to the new one.
        again = self.broker.submit(self.intent("buy", "10", nonce="1"))
        self.assertEqual(again.broker_order_id, "shadow-1")

    def test_the_state_file_is_private_whole_json_with_money_as_strings(self):
        self.buy("10")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])  # no temp file left
        state = json.loads(self.path.read_text())
        self.assertEqual(state["cash"], "993.6350")
        self.assertEqual(state["positions"][event().key]["quantity"], "10")
        self.assertEqual(state["orders"][0]["fees"], "0.1650")

    def test_a_write_that_fails_takes_the_order_back(self):
        resting = self.buy("10", limit_price="0.60")
        with mock.patch("league.paper.os.replace", side_effect=OSError("No space left on device")):
            with self.assertRaises(VenueUnavailable):
                self.buy("10")
            self.data.set(BTC, "0.57", "0.59")
            with self.assertRaises(VenueUnavailable):
                self.broker.advance()
        self.assertEqual(self.cash_now(), D(1000))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.get_order(resting.id).status, "accepted")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])
        self.assertEqual(self.broker.advance(), 1)  # the disk is back: the fill is made, once
        self.assertEqual(self.buy("1").broker_order_id, "shadow-2")
        self.assertEqual(self.new_broker().balance().cash, self.cash_now())

    def test_a_state_file_that_cannot_be_read_is_an_error_not_a_new_account(self):
        self.buy("10")
        good = self.path.read_text()
        with self.assertRaises(BrokerError):
            KalshiShadowBroker(self.path, self.data, venue="kalshi-shadow-2", clock=self.clock)
        self.path.write_text(good[: len(good) // 2])
        with self.assertRaises(BrokerError):
            self.new_broker()
        self.assertEqual(self.path.read_text(), good[: len(good) // 2])  # and it is left as it was found


class _Transport:
    """What `ltcm.data` reads through: `get(url, headers, timeout) -> (status, headers, body)`."""

    def __init__(self):
        self.markets = {}

    def get(self, url, headers=None, timeout=None):
        ticker = url.rsplit("/", 1)[-1]
        if ticker not in self.markets:
            return 404, {}, b"{}"
        return 200, {}, json.dumps({"market": self.markets[ticker]}).encode()


class RealMarketDataTest(ShadowCase):
    """The production source, `KalshiMarketData`, over Kalshi's own field names."""

    def row(self, **kw):
        return {
            "ticker": BTC, "status": "active", "result": "", "close_time": "2027-01-01T00:00:00Z",
            "yes_bid_dollars": "0.6000", "yes_ask_dollars": "0.6200", "last_price_dollars": "0.6100",
            "price_ranges": [{"start": "0.0100", "end": "0.9900", "step": "0.0100"}], **kw,
        }

    def test_orders_fill_and_settle_on_the_venues_own_rows(self):
        transport = _Transport()
        transport.markets[BTC] = self.row()
        self.data = KalshiMarketData(transport, clock=self.clock)
        self.broker = self.new_broker()
        no = self.buy("10", instrument=event("no"))
        self.assertEqual((no.status, no.average_price), ("filled", D("0.4000")))
        self.assertEqual(self.broker.quote(event("no")).instrument.venue, VENUE)
        resting = self.buy("10", limit_price="0.60", post_only=True)
        self.assertEqual(resting.status, "accepted")
        with self.assertRaises(RejectedOrder):
            self.buy("10", limit_price="0.605")
        transport.markets[BTC] = self.row(yes_bid_dollars="0.5700", yes_ask_dollars="0.5900")
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.broker.get_order(resting.id).average_price, D("0.60"))
        transport.markets[BTC] = self.row(status="finalized", result="no", yes_bid_dollars="0.0000", yes_ask_dollars="0.0000")
        rows = self.broker.settlements()
        self.assertEqual((rows[0]["result"], rows[0]["yes_count"], rows[0]["no_count"], rows[0]["revenue"]), ("no", D(10), D(10), D(10)))
        self.assertEqual(self.buy("1").status, "rejected")


class BookIntegrationTest(ShadowCase):
    cash = "100000"

    def setUp(self):
        super().setUp()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.book = Book(VENUE, self.broker, self.ledger, fees=Fees("kalshi"), real_money=False, clock=self.clock)
        for agent in ("maker", "taker"):
            self.book.limits[agent] = Limits(D(50), D(50))
            self.book.stake(agent, "100")

    def tearDown(self):
        self.ledger.close()
        super().tearDown()

    def wish(self, agent, instrument, side, quantity, **kw):
        self.n += 1
        return Intent.new(agent=agent, instrument=instrument, side=side, quantity=quantity, reason=f"test {self.n}", created_at=iso(self.clock), nonce=str(self.n), **kw)

    def test_two_agents_one_shadow_account(self):
        self.data.set(ETH, "0.90", "0.92")
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.baseline_cash, D(100000))
        wishes = [
            self.wish("maker", event(), "buy", "10", order_type="limit", limit_price="0.60", post_only=True),
            self.wish("taker", event("yes", ETH), "buy", "5"),
            self.wish("taker", event("no", ETH), "buy", "20", order_type="limit", limit_price="0.10"),
        ]
        outcomes = {o.intent_id: o for o in self.book.submit(wishes)}  # market orders are answered last
        rest, take, against = (outcomes[w.id] for w in wishes)
        self.assertEqual((rest.status, take.status, take.filled), ("resting", "filled", D(5)))
        self.assertEqual(against.status, "refused")  # the Book's longshot rule, before the broker is asked
        maker, taker = self.book.account("maker"), self.book.account("taker")
        taker_fee = Fees("kalshi").charge(event("yes", ETH), "buy", D(5), D("0.92")).usd
        self.assertEqual(taker.cash, D(100) - D("4.60") - taker_fee)
        self.assertEqual(maker.cash, D(100))
        self.assertTrue(self.book.reconcile().ok)

        # The market trades through the resting bid: the shadow fills it, the next poll books it.
        self.data.set(BTC, "0.57", "0.59")
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual(self.book.poll(), 1)
        self.assertEqual(maker.cash, D(100) - D("6.00"))  # at its own price, as a maker, no fee
        self.assertEqual(maker.holdings[event().key].quantity, D(10))
        self.assertEqual(self.book.open_orders(), [])
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))

        # The maker offers it out above the market and is lifted.
        offer = self.book.submit([self.wish("maker", event(), "sell", "10", order_type="limit", limit_price="0.64", post_only=True)])[0]
        self.assertEqual(offer.status, "resting")
        self.data.set(BTC, "0.65", "0.67")
        self.assertEqual(self.broker.advance(), 1)
        self.book.poll()
        self.assertEqual((maker.cash, maker.realized, maker.holdings), (D("100.40"), D("0.40"), {}))
        self.assertTrue(self.book.reconcile().ok)

        # The taker's market resolves YES: the shadow pays the account, the Book pays the agent.
        self.data.rows[ETH] = {"status": "finalized", "result": "yes"}
        rows = self.broker.settlements()
        self.assertEqual([(r["ticker"], r["result"], r["revenue"]) for r in rows], [(ETH, "yes", D(5))])
        for row in rows:
            self.assertEqual(self.book.settle(row["ticker"], row["result"]), 1)
        self.assertEqual(taker.cash, D(100) - D("4.60") - taker_fee + D(5))
        self.assertEqual(taker.holdings, {})
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))
        self.assertIsNone(self.book.frozen)
        self.assertEqual(self.broker.balance().cash, D(100000) + (maker.cash - 100) + (taker.cash - 100))
        self.assertEqual(self.broker.positions(), [])


if __name__ == "__main__":
    unittest.main()

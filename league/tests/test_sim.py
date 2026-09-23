import json
import os
import stat
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ltcm.broker import Broker, BrokerError, Instrument, OrderIntent, RejectedOrder, VenueUnavailable

from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import HOUSE, Ledger
from league.sim import CAPABILITIES, SimBroker, touch_from
from league.tests.fakes import Clock, iso

D = Decimal
VENUE = "alpaca-paper"
BTC = Instrument("crypto", "BTC-USD", VENUE, market_id="BTC/USD")
ETH = Instrument("crypto", "ETH-USD", VENUE, market_id="ETH/USD")
SPY = Instrument("equity", "SPY", VENUE)


class Touches:
    """The quote source of a test: a dictionary, and a switch that takes it down."""

    def __init__(self):
        self.rows = {}
        self.down = False
        self.calls = 0

    def set(self, instrument, bid, ask):
        self.rows[instrument.key] = (D(bid), D(ask))

    def __call__(self, instrument):
        self.calls += 1
        if self.down:
            raise RuntimeError("the source is down")
        return self.rows.get(instrument.key)


class SimCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "sim" / "alpaca-paper.json"
        self.clock = Clock()
        self.touch = Touches()
        self.touch.set(BTC, "80000", "80010")
        self.touch.set(SPY, "50.00", "50.02")
        self.broker = self.open()
        self.n = 0

    def tearDown(self):
        self.dir.cleanup()

    def open(self, **kw):
        return SimBroker(self.path, self.touch, clock=self.clock, **kw)

    def intent(self, instrument, side, quantity, **kw):
        self.n += 1
        return OrderIntent.new(
            desk_id="book-alpaca-paper", instrument=instrument, side=side, quantity=quantity,
            order_type=kw.pop("order_type", "market"), limit_price=kw.pop("limit_price", None),
            time_in_force=kw.pop("time_in_force", "gtc"), rationale="a test", created_at=iso(self.clock),
            nonce=kw.pop("nonce", str(self.n)), **kw,
        )

    def held(self, broker=None):
        return {p.instrument.symbol: p.quantity for p in (broker or self.broker).positions()}


class SurfaceTest(SimCase):
    def test_it_is_a_broker_that_sends_nothing(self):
        self.assertIsInstance(self.broker, Broker)
        self.assertEqual(self.broker.capabilities(), set(CAPABILITIES))
        self.assertIn("shadow", self.broker.capabilities())
        self.assertNotIn("short", self.broker.capabilities())
        balance = self.broker.balance()
        self.assertEqual((balance.venue, balance.cash, balance.equity), (VENUE, D("100000"), D("100000")))
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.broker.open_orders(), [])
        self.assertEqual(self.broker.fills(), [])

    def test_quote_is_the_touch_and_no_touch_is_an_error(self):
        quote = self.broker.quote(BTC)
        self.assertEqual((quote.bid, quote.ask, quote.delayed, quote.as_of), (D("80000"), D("80010"), False, iso(self.clock)))
        with self.assertRaises(VenueUnavailable):
            self.broker.quote(ETH)
        self.touch.down = True
        with self.assertRaises(VenueUnavailable):
            self.broker.quote(BTC)

    def test_an_order_is_accepted_first_and_fills_on_the_next_read(self):
        order = self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.filled_quantity, D(0))
        self.assertEqual(self.broker.positions(), [])  # nothing has happened yet
        self.assertEqual(self.broker.balance().cash, D("100000"))
        self.assertEqual(self.broker.balance().buying_power, D("100000") - D("40.005"))  # but the cash is held
        read = self.broker.get_order(order.broker_order_id)
        self.assertEqual((read.status, read.filled_quantity, read.average_price), ("filled", D("0.0005"), D("80010")))
        # Measured: the 0.25% taker fee comes out of the coins, cash pays the touch and no more,
        # the adapter reports a fee of zero, and the position is spelled without its slash.
        self.assertEqual(read.fees, D(0))
        self.assertEqual(self.held(), {"BTCUSD": D("0.00049875")})
        self.assertEqual(self.broker.balance().cash, D("100000") - D("40.005"))
        self.assertEqual(self.broker.get_order(order.id).status, "filled")  # by either id, and only once
        self.assertEqual(self.held(), {"BTCUSD": D("0.00049875")})

    def test_a_market_order_fills_at_the_touch_of_the_read_not_of_the_submit(self):
        order = self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.touch.set(BTC, "80100", "80110")
        self.assertEqual(self.broker.get_order(order.id).average_price, D("80110"))

    def test_a_sell_pays_its_fee_from_the_proceeds_rounded_up_to_the_cent(self):
        self.broker.get_order(self.broker.submit(self.intent(BTC, "buy", "0.0005")).id)
        cash = self.broker.balance().cash
        self.touch.set(BTC, "82000", "82010")
        sold = self.broker.get_order(self.broker.submit(self.intent(BTC, "sell", "0.00049875")).id)
        self.assertEqual(sold.status, "filled")
        proceeds = D("0.00049875") * D("82000")  # 40.8975; 0.25% of it is 0.1022..., charged as 0.11
        self.assertEqual(self.broker.balance().cash, cash + proceeds - D("0.11"))
        self.assertEqual(self.broker.positions(), [])
        fills = self.broker.fills()
        self.assertEqual([(f.side, f.fee) for f in fills], [("buy", D(0)), ("sell", D("0.11"))])
        self.assertEqual(self.broker.fills(since=fills[1].at), fills)  # one clock instant: both are at or after it
        self.clock.advance(5)
        self.assertEqual(self.broker.fills(since=iso(self.clock)), [])
        with self.assertRaises(ValueError):
            self.broker.fills(since="yesterday")

    def test_equities_pay_nothing(self):
        bought = self.broker.get_order(self.broker.submit(self.intent(SPY, "buy", "1.5", time_in_force="day")).id)
        self.assertEqual(bought.status, "filled")
        self.assertEqual(self.held(), {"SPY": D("1.5")})
        self.assertEqual(self.broker.balance().cash, D("100000") - D("75.03"))
        self.broker.get_order(self.broker.submit(self.intent(SPY, "sell", "1.5", time_in_force="day")).id)
        self.assertEqual(self.broker.balance().cash, D("100000") - D("75.03") + D("75.00"))

    def test_no_market_no_market_order_and_a_blind_read_decides_nothing(self):
        refused = self.broker.submit(self.intent(ETH, "buy", "0.01"))
        self.assertEqual((refused.status, refused.terminal), ("rejected", True))
        self.assertIn("no market", refused.reason)
        waiting = self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.touch.down = True
        self.assertEqual(self.broker.get_order(waiting.id).status, "accepted")
        self.assertEqual([o.id for o in self.broker.open_orders()], [waiting.id])
        self.touch.down = False
        self.assertEqual(self.broker.open_orders(), [])  # the read that could see the market filled it
        self.assertEqual(self.broker.get_order(waiting.id).status, "filled")

    def test_a_marketable_limit_takes_the_touch(self):
        order = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="80500"))
        self.assertEqual(order.status, "accepted")
        read = self.broker.get_order(order.id)
        self.assertEqual((read.status, read.average_price), ("filled", D("80010")))  # the ask, not its limit
        self.assertEqual(self.held(), {"BTCUSD": D("0.00049875")})  # a taker

    def test_a_limit_rests_until_the_touch_crosses_it_then_makes_at_its_own_price(self):
        order = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000"))
        for _ in range(3):
            self.assertEqual(self.broker.get_order(order.id).status, "accepted")
        self.assertEqual([o.id for o in self.broker.open_orders()], [order.id])
        self.assertEqual(self.broker.balance().buying_power, D("100000") - D("39.5"))
        self.touch.set(BTC, "78900", "78950")
        self.assertEqual(self.broker.advance(), 1)
        read = self.broker.get_order(order.id)
        self.assertEqual((read.status, read.average_price), ("filled", D("79000")))  # its price, not the better touch
        self.assertEqual(self.held(), {"BTCUSD": D("0.0005") - D("0.00000075")})  # the maker's 0.15%
        self.assertEqual(self.broker.balance().cash, D("100000") - D("39.5"))
        self.assertEqual(self.broker.advance(), 0)

    def test_a_resting_sell_fills_when_the_bid_reaches_it(self):
        self.broker.get_order(self.broker.submit(self.intent(SPY, "buy", "2", time_in_force="day")).id)
        order = self.broker.submit(self.intent(SPY, "sell", "2", order_type="limit", limit_price="51.00", time_in_force="day"))
        self.assertEqual([o.id for o in self.broker.open_orders()], [order.id])
        self.touch.set(SPY, "51.00", "51.03")
        self.assertEqual(self.broker.open_orders(), [])
        self.assertEqual(self.broker.get_order(order.id).average_price, D("51.00"))
        self.assertEqual(self.broker.positions(), [])

    def test_post_only_never_takes(self):
        crossing = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="80010", post_only=True))
        self.assertEqual((crossing.status, crossing.reason), ("rejected", "post-only order would cross"))
        resting = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="80005", post_only=True))
        self.assertEqual(resting.status, "accepted")
        self.touch.set(BTC, "79990", "80000")  # the market moved through it before anyone read it
        read = self.broker.get_order(resting.id)
        self.assertEqual((read.status, read.average_price), ("filled", D("80005")))  # still a maker, at its price
        self.assertEqual(self.held(), {"BTCUSD": D("0.0005") - D("0.00000075")})

    def test_an_ioc_that_does_not_cross_is_cancelled(self):
        order = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000", time_in_force="ioc"))
        read = self.broker.get_order(order.id)
        self.assertEqual(read.status, "cancelled")
        self.assertIn("immediate-or-cancel", read.reason)
        self.assertEqual(self.broker.balance().buying_power, D("100000"))

    def test_cancel_reads_first(self):
        resting = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000"))
        self.assertEqual(self.broker.cancel(resting.broker_order_id).status, "cancelled")
        self.assertEqual(self.broker.cancel(resting.id).status, "cancelled")  # again is no error
        self.assertEqual(self.broker.balance().buying_power, D("100000"))
        self.touch.set(BTC, "78000", "78010")
        self.assertEqual(self.broker.advance(), 0)  # a cancelled order never fills
        market = self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.assertEqual(self.broker.cancel(market.id).status, "filled")  # too late, as at the venue

    def test_submit_is_idempotent_on_the_intent(self):
        intent = self.intent(BTC, "buy", "0.0005")
        first = self.broker.submit(intent)
        again = self.broker.submit(intent)
        self.assertEqual((again.id, again.broker_order_id), (first.id, first.broker_order_id))
        self.broker.get_order(first.id)
        after = self.broker.submit(intent)  # even once it has filled: the stored order, nothing new
        self.assertEqual((after.status, after.broker_order_id), ("filled", first.broker_order_id))
        self.assertEqual(len(self.broker.fills()), 1)
        self.assertEqual(self.held(), {"BTCUSD": D("0.00049875")})

    def test_no_leverage_and_no_shorts_at_the_account(self):
        small = SimBroker(Path(self.dir.name) / "small.json", self.touch, starting_cash="50", clock=self.clock)
        first = small.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000"))
        self.assertEqual(first.status, "accepted")  # $39.50 of the $50 is now spoken for
        second = small.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000"))
        self.assertEqual(second.status, "rejected")
        self.assertIn("insufficient buying power", second.reason)
        short = small.submit(self.intent(BTC, "sell", "0.0001"))
        self.assertEqual(short.status, "rejected")
        self.assertIn("no shorts", short.reason)
        # Units offered by one resting sell cannot be offered again.
        self.broker.get_order(self.broker.submit(self.intent(SPY, "buy", "2", time_in_force="day")).id)
        self.assertEqual(self.broker.submit(self.intent(SPY, "sell", "2", order_type="limit", limit_price="60", time_in_force="day")).status, "accepted")
        self.assertEqual(self.broker.submit(self.intent(SPY, "sell", "1", time_in_force="day")).status, "rejected")

    def test_what_the_venue_would_not_take_is_refused_and_not_recorded(self):
        cases = [
            self.intent(Instrument("crypto", "BTC-USD", "alpaca", market_id="BTC/USD"), "buy", "0.0005"),
            self.intent(Instrument("event", "KXBTCD-X", VENUE, market_id="KXBTCD-X", right="yes"), "buy", "1"),
            self.intent(SPY, "buy", "1.5", order_type="limit", limit_price="50", time_in_force="gtc"),  # fractional shares are day orders
            self.intent(BTC, "buy", "0.00000000015"),
        ]
        for intent in cases:
            with self.assertRaises(RejectedOrder):
                self.broker.submit(intent)
        self.assertEqual(json.loads(self.path.read_text())["orders"], [])
        with self.assertRaises(RejectedOrder):
            self.broker.get_order("ord-nobody")
        with self.assertRaises(RejectedOrder):
            self.broker.cancel("sim-99")

    def test_one_spelling_of_a_pair_is_one_position(self):
        self.broker.get_order(self.broker.submit(self.intent(BTC, "buy", "0.0005")).id)
        slashed = Instrument("crypto", "BTC/USD", VENUE)
        self.touch.set(slashed, "80000", "80010")
        self.broker.get_order(self.broker.submit(self.intent(slashed, "buy", "0.0005")).id)
        self.assertEqual(self.held(), {"BTCUSD": D("0.0009975")})


class FractionalLimitTest(SimCase):
    def test_a_fractional_equity_limit_order_rests_as_a_day_order_and_no_other(self):
        """A7 (Sept 23, 2026): the practice simulator takes what Alpaca takes, a fractional limit order with `day`."""
        order = self.broker.submit(self.intent(SPY, "buy", "0.25", order_type="limit", limit_price="49.98", time_in_force="day"))
        self.assertEqual((order.status, order.quantity), ("accepted", D("0.25")))
        self.assertEqual(self.broker.get_order(order.id).status, "accepted")  # resting under the ask, not rounded away
        with self.assertRaises(RejectedOrder) as refused:
            self.broker.submit(self.intent(SPY, "buy", "0.25", order_type="limit", limit_price="49.98", time_in_force="gtc"))
        self.assertIn("day order", str(refused.exception))
        whole = self.broker.submit(self.intent(SPY, "buy", "1", order_type="limit", limit_price="49.98", time_in_force="gtc"))
        self.assertEqual(whole.status, "accepted")


class PersistenceTest(SimCase):
    def test_the_file_is_private_and_a_restart_loses_nothing(self):
        filled = self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.broker.get_order(filled.id)
        resting = self.broker.submit(self.intent(BTC, "buy", "0.0005", order_type="limit", limit_price="79000"))
        self.broker.get_order(resting.id)
        pending = self.intent(SPY, "buy", "1", time_in_force="day")
        self.broker.submit(pending)  # accepted, never read: the restart must still fill it
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])  # no temp file left behind

        again = self.open(starting_cash="1")  # starting cash only matters when there is no file
        # The $40.005 it paid, and (as the real paper venue does) the $39.50 behind the resting bid.
        self.assertEqual(again.balance().cash, D("100000") - D("40.005") - D("39.5"))
        self.assertEqual(self.held(again), {"BTCUSD": D("0.00049875")})
        self.assertEqual(again.fills(), self.broker.fills())
        self.assertEqual(again.submit(pending).broker_order_id, "sim-3")  # idempotent across the restart
        self.assertEqual({o.id for o in again.open_orders()}, {resting.id})  # the read filled the pending share
        self.assertEqual(self.held(again), {"BTCUSD": D("0.00049875"), "SPY": D("1")})
        self.touch.set(BTC, "78900", "78950")
        self.assertEqual(again.get_order(resting.id).average_price, D("79000"))  # it remembered it had rested
        self.assertEqual(again.submit(self.intent(BTC, "sell", "0.0001")).broker_order_id, "sim-4")  # and its counter

    def test_a_file_that_cannot_be_read_is_an_error_never_a_fresh_account(self):
        self.path.write_text("{not json")
        with self.assertRaises(BrokerError):
            self.open()
        self.path.write_text(json.dumps({"version": 99}))
        with self.assertRaises(BrokerError):
            self.open()
        other = Path(self.dir.name) / "other.json"
        SimBroker(other, self.touch, venue="alpaca-canary")
        with self.assertRaises(BrokerError):
            SimBroker(other, self.touch, venue=VENUE)

    def test_a_write_that_fails_takes_the_order_back(self):
        with mock.patch("league.sim.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(VenueUnavailable):
                self.broker.submit(self.intent(BTC, "buy", "0.0005"))
        self.assertEqual(self.broker.open_orders(), [])
        self.assertEqual(self.broker.balance().buying_power, D("100000"))
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])

    def test_constructor_refusals(self):
        with self.assertRaises(TypeError):
            SimBroker(Path(self.dir.name) / "x.json", {"BTC": (1, 2)})
        with self.assertRaises(ValueError):
            SimBroker(Path(self.dir.name) / "y.json", self.touch, starting_cash="-1")


class TouchFromTest(unittest.TestCase):
    class Data:
        def __init__(self):
            self.calls = []
            self.rows = {"BTC/USD": {"bid": 80000.5, "ask": 80010.25}, "SPY": {"bid": 50.0, "ask": 50.02}}

        def quotes(self, symbols):
            self.calls.append(list(symbols))
            return {s: self.rows[s] for s in symbols if s in self.rows}

    def test_it_reads_alpaca_data_in_alpacas_spelling_and_holds_it_briefly(self):
        clock, data = Clock(), self.Data()
        quotes = touch_from(data, ttl=5, clock=clock)
        self.assertEqual(quotes(BTC), (D("80000.5"), D("80010.25")))  # floats in, exact decimals out
        self.assertEqual(quotes(BTC), (D("80000.5"), D("80010.25")))
        self.assertEqual(quotes(SPY), (D("50.0"), D("50.02")))
        self.assertIsNone(quotes(ETH))  # no two-sided quote at the venue
        self.assertIsNone(quotes(Instrument("event", "KX", VENUE, market_id="KX")))
        self.assertEqual(data.calls, [["BTC/USD"], ["SPY"], ["ETH/USD"]])
        clock.advance(6)
        quotes(BTC)
        self.assertEqual(data.calls[-1], ["BTC/USD"])
        self.assertEqual(len(data.calls), 4)

    def test_a_sim_broker_on_it_fills_at_those_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = Clock()
            broker = SimBroker(Path(tmp) / "a.json", touch_from(self.Data(), clock=clock), clock=clock)
            intent = OrderIntent.new(desk_id="d", instrument=BTC, side="buy", quantity="0.0005", time_in_force="gtc", rationale="r", created_at=iso(clock))
            self.assertEqual(broker.get_order(broker.submit(intent).id).average_price, D("80010.25"))


class ThroughTheBookTest(SimCase):
    """The canary's real path: `league.book.Book` over a `SimBroker`, reconciled at every stage."""

    def setUp(self):
        super().setUp()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.book = self.new_book(self.broker)

    def tearDown(self):
        self.ledger.close()
        super().tearDown()

    def new_book(self, broker):
        book = Book(VENUE, broker, self.ledger, fees=Fees("alpaca"), real_money=False, clock=self.clock)
        for agent in ("ann", "bob"):
            book.limits[agent] = Limits(D("100"), D("75"))
        return book

    def want(self, agent, instrument, side, quantity, **kw):
        self.n += 1
        return Intent.new(agent=agent, instrument=instrument, side=side, quantity=quantity, reason=f"test {self.n}",
                          created_at=iso(self.clock), nonce=str(self.n), **kw)

    def reconciled(self, book=None):
        result = (book or self.book).reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone((book or self.book).frozen)
        return result

    def test_two_agents_a_cross_a_resting_order_and_a_restart_all_reconcile(self):
        book = self.book
        self.reconciled()  # the House opens every book's baseline before anything trades
        self.assertEqual(book.baseline_cash, D("100000"))
        book.stake("ann", "200")
        book.stake("bob", "200")

        # 1. Ann buys at the market: accepted first, a taker's fill on the next poll.
        out = book.submit([self.want("ann", BTC, "buy", "0.0006")])[0]
        self.assertEqual(out.status, "sent")
        self.assertEqual(book.account("ann").holdings, {})
        book.poll()
        held = book.account("ann").holdings[BTC.key].quantity
        self.assertEqual(held, D("0.0005985"))
        self.assertEqual(book.account("ann").cash, D("200") - D("0.0006") * D("80010"))
        self.assertEqual(book.open_orders(), [])
        self.reconciled()

        # 2. Bob buys while Ann sells: crossed inside the House, only the difference reaches the venue.
        orders_before = len(json.loads(self.path.read_text())["orders"])
        outs = {o.agent: o for o in book.submit([self.want("bob", BTC, "buy", "0.0005"), self.want("ann", BTC, "sell", str(held))])}
        self.assertEqual(outs["bob"].status, "crossed")
        sent = json.loads(self.path.read_text())["orders"][orders_before:]
        self.assertEqual([(o["side"], o["quantity"]) for o in sent], [("sell", format(held - D("0.0005"), "f"))])
        book.poll()
        self.assertEqual(book.account("ann").holdings, {})
        self.assertEqual(book.account("bob").holdings[BTC.key].quantity, D("0.00049875"))
        self.assertEqual(book.account("bob").cash, D("200") - D("0.0005") * D("80010"))  # the ask, as if alone
        self.assertGreater(book.account(HOUSE).cash, 0)  # the spread and fee the account never paid
        self.assertEqual({p.instrument.symbol: p.quantity for p in self.broker.positions()}, {"BTCUSD": D("0.0005")})
        self.reconciled()

        # 3. Bob rests a bid under the market. It reconciles while it rests, and when the market
        #    comes down through it: the venue charged a maker, the book assumed a taker, and the
        #    coins in between go to the House inside the known allowance.
        rest = book.submit([self.want("bob", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.assertEqual(rest.status, "resting")
        book.poll()
        self.assertEqual(len(book.open_orders("bob")), 1)
        self.reconciled()
        self.clock.advance(60)
        self.touch.set(BTC, "78900", "78950")
        book.poll()
        self.assertEqual(book.open_orders(), [])
        self.assertEqual(book.account("bob").holdings[BTC.key].quantity, D("0.00049875") * 2)
        row = book.account(HOUSE).holdings.get(BTC.key)
        house_before = row.quantity if row else D(0)
        self.reconciled()
        self.assertEqual(book.account(HOUSE).holdings[BTC.key].quantity - house_before, D("0.0000005"))
        self.reconciled()

        # 4. A share, which pays nothing, and Ann back in through a marketable limit.
        self.assertEqual(book.submit([self.want("ann", SPY, "buy", "1")])[0].status, "sent")
        self.assertEqual(book.submit([self.want("ann", BTC, "buy", "0.0004", order_type="limit", limit_price="79500")])[0].status, "resting")
        book.poll()
        self.assertEqual(book.account("ann").holdings[SPY.key].quantity, D("1"))
        self.assertEqual(book.account("ann").holdings[BTC.key].quantity, D("0.000399"))  # took the 78950 ask
        book.mark()
        self.reconciled()

        # 5. Both halves restart: the account from its file, the book from the ledger.
        reopened = self.new_book(self.open())
        self.assertEqual(reopened.account("bob").cash, book.account("bob").cash)
        self.assertEqual(reopened.account("ann").holdings[BTC.key].quantity, D("0.000399"))
        result = self.reconciled(reopened)
        self.assertEqual(result.cash_diff, D(0))
        self.assertEqual(result.position_diffs, {})
        self.assertGreater(self.ledger.verify(), 20)

    def test_a_second_trader_on_the_account_is_exactly_what_breaks_a_book(self):
        """Why the canary gets its own account: anyone else's fill is a mismatch the book freezes on."""
        self.reconciled()
        self.book.stake("ann", "200")
        self.book.submit([self.want("ann", BTC, "buy", "0.0005")])
        self.book.poll()
        self.reconciled()
        stranger = OrderIntent.new(desk_id="someone-else", instrument=BTC, side="buy", quantity="0.0005", time_in_force="gtc", rationale="r", created_at=iso(self.clock))
        self.broker.get_order(self.broker.submit(stranger).id)
        self.assertFalse(self.book.reconcile().ok)
        self.assertIsNotNone(self.book.frozen)


if __name__ == "__main__":
    unittest.main()

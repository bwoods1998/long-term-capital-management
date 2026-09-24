"""D3 (Sept 24, 2026): an exit is never refused for crossing the House's own resting order.

Evidence (T0 snapshot, 01:42Z Sept 24): `Book._would_cross_own` refused "a market order here could
trade against the House's own resting order" 130 times in the ledger's life, 108 in the 48 hours
before T0 (74 of them sells), 16 in the last hour. Every crossing order was a PEER's resting limit
bid on the practice Alpaca book: the alpaca-crypto-alts desk's mean-reversion agents all rest bids
under the mean, so each one's time stop met a sibling's bid on every wake. At 01:15:07Z haghani-
hb85bb8's market exit of 1.614256644 LINK/USD ("Exit at the time stop or defined 2.5% adverse-move
stop") met five: haghani-59 3.138088471 @ 12.173015625, haghani-55 3.148636721 @ 12.158965625,
haghani-37 3.032330309 @ 12.158965625, haghani-57 3.292181069 @ 12.15, haghani-56 2.074434872 @
12.051475. The tests below are built from that shape.
"""

import copy
import unittest
from decimal import Decimal
from unittest.mock import patch

from ltcm.broker import BrokerError, Instrument, RejectedOrder

from league.auditor import order_outcomes
from league.book import q_cash
from league.fees import Fees, received
from league.ledger import HOUSE
from league.tests.test_book import BookCase

D = Decimal

#: The snapshot's five resting bids at 01:15:07Z, best first: (agent, quantity, limit).
BIDS = (
    ("haghani-59", "3.138088471", "12.173015625"),
    ("haghani-55", "3.148636721", "12.158965625"),
    ("haghani-37", "3.032330309", "12.158965625"),
    ("haghani-57", "3.292181069", "12.15"),
    ("haghani-56", "2.074434872", "12.051475"),
)
EXIT_REASON = "Exit at the time stop or defined 2.5% adverse-move stop"


def link(venue):
    return Instrument("crypto", "LINK-USD", venue, market_id="LINK/USD")


def event(leg="yes", ticker="KXBTCD-26SEP2401-T62999.99", venue="kalshi"):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


class CrossCase(BookCase):
    """A book with the venue read once (as the House does at start), and helpers to hold and bid."""

    def setUp(self):
        self.slept = []  # the book's waits for a cancel to be confirmed, recorded instead of slept
        super().setUp()
        self.book.reconcile()

    def new_book(self):
        book = super().new_book()
        book.sleep = self.slept.append
        return book

    def rest_bid(self, agent, instrument, quantity, price, *, usd="200", post_only=False):
        if agent not in self.book.limits:
            self.seat(agent, usd=usd)
        out = self.book.submit([self.intent(agent, instrument, "buy", quantity, order_type="limit", limit_price=price,
                                            post_only=post_only)])[0]
        self.assertEqual(out.status, "resting", out.detail)
        return out.order_id

    def hold(self, agent, instrument, quantity, *, usd="200"):
        """Hold `quantity` of `instrument`: a market buy on Alpaca, a resting bid filled as a maker on
        Kalshi (a real Kalshi entry may be post-only only, X0)."""
        if agent not in self.book.limits:
            self.seat(agent, usd=usd)
        if instrument.asset_class == "event":
            _, ask = self.broker.quotes[instrument.key]
            bid = ask - D("0.01")
            out = self.book.submit([self.intent(agent, instrument, "buy", quantity, order_type="limit", limit_price=bid,
                                                post_only=True)])[0]
            self.assertEqual(out.status, "resting", out.detail)
            self.broker.fill_resting(out.order_id, quantity)
            self.book.poll()
        else:
            out = self.book.submit([self.intent(agent, instrument, "buy", quantity)])[0]
            self.assertEqual(out.status, "filled", out.detail)
        return self.book.account(agent).holdings[instrument.key].quantity

    def crossed_fills(self, agent):
        return [e.payload for e in self.ledger.iter(kinds="book.fill", agent=agent) if e.payload.get("source") == "cross"]

    def snapshot_state(self):
        return {name: (a.cash, a.staked, a.realized, a.fees, {k: (h.quantity, h.cost) for k, h in a.holdings.items()})
                for name, a in self.book.accounts.items()}


class PracticeAlpacaExitTest(CrossCase):
    venue, family, real, cash = "alpaca-paper", "alpaca", False, "100000"

    def setUp(self):
        super().setUp()
        self.inst = link(self.venue)
        # The House's own bids in these tests stand at the market's bid (12.17), where a sell at the
        # venue would really meet them; `test_bids_under_the_market...` has them under it.
        self.broker.set_quote(self.inst, "12.17", "12.19")
        self.broker.reserve_open_buys = True  # Alpaca holds the cash behind a resting crypto bid out of `cash`

    def snapshot_bids(self):
        return {agent: self.rest_bid(agent, self.inst, quantity, price) for agent, quantity, price in BIDS}

    def test_the_snapshots_exit_crosses_the_best_peer_bid_inside_the_house(self):
        held = self.hold("haghani-hb85bb8", self.inst, "1.62")
        orders = self.snapshot_bids()
        sent_before = len(self.broker.submitted)
        cash_before = self.book.account("haghani-hb85bb8").cash
        out = self.book.submit([self.intent("haghani-hb85bb8", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual(out.status, "crossed", out.detail)  # was "refused"
        self.assertEqual(out.filled, held)
        self.assertIn("haghani-59", out.detail)
        self.assertEqual(len(self.broker.submitted), sent_before)  # nothing went to the venue for the exit
        # Only the best bid was cancelled at the venue; the other four still rest.
        self.assertEqual(self.broker.cancelled, [orders["haghani-59"]])
        self.assertFalse(self.book.orders[orders["haghani-59"]].open)
        for agent in ("haghani-55", "haghani-37", "haghani-57", "haghani-56"):
            self.assertTrue(self.book.orders[orders[agent]].open)
        # The exiter sold at what the venue would have paid it alone -- the market's bid, 12.17, not the House bid's
        # 12.173015625 (review of #226) -- and paid the taker's fee, in cash, as the venue would.
        price, bid = D("12.17"), D("12.173015625")
        taker = Fees("alpaca").charge(self.inst, "sell", held, price, liquidity="taker")
        self.assertEqual(self.book.account("haghani-hb85bb8").holdings, {})
        self.assertEqual(self.book.account("haghani-hb85bb8").cash, cash_before + q_cash(held * price - taker.usd))
        # The peer bought at its own limit as a maker: the fee comes out of the coins.
        maker = Fees("alpaca").charge(self.inst, "buy", held, bid, liquidity="maker")
        peer = self.book.account("haghani-59")
        self.assertEqual(peer.holdings[self.inst.key].quantity, received(held, maker))
        self.assertEqual(peer.cash, D("200") - q_cash(held * bid))
        (sold,) = self.crossed_fills("haghani-hb85bb8")
        (bought,) = self.crossed_fills("haghani-59")
        self.assertEqual((sold["side"], sold["liquidity"], D(sold["price"])), ("sell", "taker", price))
        self.assertEqual((bought["side"], bought["liquidity"], D(bought["price"])), ("buy", "maker", bid))
        self.assertEqual(sold["resting_orders"], [orders["haghani-59"]])
        self.assertEqual(bought["resting_order"], orders["haghani-59"])
        self.assertIsNotNone(sold["realized"])
        # The House row holds what the venue never charged: the taker's cash fee, the maker's coins.
        house = self.book.account(HOUSE)
        self.assertEqual(house.holdings[self.inst.key].quantity, maker.quantity)
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.ledger.verify()
        # The rest of haghani-59's bid is not re-placed, and its record says so.
        self.assertEqual(self.book.open_orders("haghani-59"), [])
        told = [row for row in order_outcomes(self.ledger, "haghani-59", self.book.name) if row.get("order_id") == orders["haghani-59"]]
        self.assertEqual(told[-1]["status"], "cancelled")
        self.assertIn("not re-placed", told[-1]["reason"])
        self.assertIn("not re-placed", bought["note"])

    def test_a_restart_rebuilds_the_crossed_book_exactly(self):
        held = self.hold("haghani-hb85bb8", self.inst, "1.62")
        self.snapshot_bids()
        self.book.submit([self.intent("haghani-hb85bb8", self.inst, "sell", held, reason=EXIT_REASON)])
        before = self.snapshot_state()
        self.book = self.new_book()
        self.assertEqual(self.snapshot_state(), before)
        self.assertFalse(self.book._cross_plans)
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.poll(), 4)  # the four bids still resting; nothing is crossed or booked again
        self.assertEqual(self.snapshot_state(), before)

    def test_the_agents_own_crossing_bid_is_cancelled_and_the_exit_goes_to_the_venue(self):
        held = self.hold("a1", self.inst, "1.62")
        own = self.rest_bid("a1", self.inst, "1", "12.17")
        out = self.book.submit([self.intent("a1", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "filled", out.detail)  # was "refused"
        self.assertEqual(self.broker.cancelled, [own])
        self.assertEqual(self.book.orders[own].status, "cancelled")
        self.assertEqual(self.broker.submitted[-1].side, "sell")
        self.assertEqual(self.broker.submitted[-1].order_type, "market")
        cancels = [e.payload for e in self.ledger.iter(kinds="book.cancel", agent="a1")]
        self.assertEqual([c["order_id"] for c in cancels], [own])
        told = [row for row in order_outcomes(self.ledger, "a1", self.book.name) if row.get("order_id") == own]
        self.assertIn("your own exit", told[-1]["reason"])
        self.assertEqual(self.crossed_fills("a1"), [])  # never a cross with itself
        self.assertEqual(self.book.account("a1").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_an_exit_larger_than_the_bid_crosses_it_and_sends_the_rest_to_the_venue(self):
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "1", "12.17")
        out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertEqual(out.filled, held)
        self.assertEqual(self.broker.cancelled, [bid])
        (crossed,) = self.crossed_fills("seller")
        self.assertEqual(D(crossed["quantity"]), D("1"))
        self.assertEqual(self.broker.submitted[-1].quantity, held - D("1"))  # the rest, at market, alone
        self.assertEqual(self.broker.submitted[-1].order_type, "market")
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_an_exit_larger_than_the_best_bid_crosses_the_next_one_too(self):
        held = self.hold("seller", self.inst, "1.62")
        self.broker.set_quote(self.inst, "12.16", "12.19")  # both bids at or above the market's bid
        first = self.rest_bid("p1", self.inst, "1", "12.17")
        second = self.rest_bid("p2", self.inst, "1", "12.16")
        out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        self.assertEqual(self.broker.cancelled, [first, second])
        (sold,) = self.crossed_fills("seller")
        self.assertEqual(sold["resting_orders"], [first, second])
        rest = held - D("1")
        self.assertEqual(D(self.crossed_fills("p1")[0]["quantity"]), D("1"))
        self.assertEqual(D(self.crossed_fills("p2")[0]["quantity"]), rest)
        self.assertEqual(D(self.crossed_fills("p1")[0]["price"]), D("12.17"))  # each bidder at its own limit
        self.assertEqual(D(self.crossed_fills("p2")[0]["price"]), D("12.16"))
        # The seller at the market's bid, 12.16, for all of it: never the 12.17 bid, which is over the market
        # (review of #226). The House row keeps the cent between them on the one unit.
        self.assertEqual(D(sold["price"]), D("12.16"))
        taker = Fees("alpaca").charge(self.inst, "sell", held, D("12.16"), liquidity="taker")
        self.assertEqual(D(sold["cash_delta"]), q_cash(held * D("12.16") - taker.usd))
        self.assertTrue(self.book.reconcile().ok)

    def test_an_unconfirmed_cancel_is_never_a_cross_the_exit_rests_post_only_at_the_ask(self):
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731 - Alpaca's pending_cancel reads as open
        with patch.object(self.broker, "cancel", side_effect=pending):
            out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "resting", out.detail)
        self.assertIn("post-only limit at the ask", out.detail)
        self.assertEqual(self.slept, [0.25, 0.25])  # read twice more, a moment apart, then given up
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.crossed_fills("buyer"), [])
        self.assertTrue(self.book.orders[bid].open)  # the book waits for the venue's word
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("12.19"), True))
        told = order_outcomes(self.ledger, "seller", self.book.name)[-1]
        self.assertIn("post-only limit at the ask", told["reason"])
        # When the venue does cancel, the poll books it: still no cross.
        self.broker.orders[bid].status = "cancelled"
        self.book.poll()
        self.assertFalse(self.book.orders[bid].open)
        self.assertEqual(self.crossed_fills("buyer"), [])
        self.assertTrue(self.book.reconcile().ok)

    def test_a_bid_whose_cancel_the_venue_confirms_late_is_told_why(self):
        """Review of #226: the House cancelled a peer's bid to cross an exit, the venue confirmed the cancel only
        after the pass had given the cross up, and the poll closed the bid with no reason at all: the peer lost
        its resting bid to the House and its record said nothing about it."""
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731 - Alpaca's pending_cancel reads as open
        with patch.object(self.broker, "cancel", side_effect=pending):
            self.book.submit([self.intent("seller", self.inst, "sell", held)])
        self.assertEqual(self.crossed_fills("buyer"), [])
        self.broker.orders[bid].status = "cancelled"  # the venue finishes the House's cancel
        self.book.poll()
        told = [row for row in order_outcomes(self.ledger, "buyer", self.book.name) if row.get("order_id") == bid][-1]
        self.assertEqual(told["status"], "cancelled")
        self.assertIn("confirmed the cancel too late for the cross, so nothing was crossed", told["reason"])

    def test_the_agents_own_later_cancel_is_not_told_as_the_houses(self):
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731
        with patch.object(self.broker, "cancel", side_effect=pending):
            self.book.submit([self.intent("seller", self.inst, "sell", held)])
        self.assertEqual(self.book.cancel("buyer", bid).status, "cancelled")  # the bidder withdraws it itself
        told = [row for row in order_outcomes(self.ledger, "buyer", self.book.name) if row.get("order_id") == bid][-1]
        self.assertEqual((told["status"], told["reason"]), ("cancelled", ""))

    def test_a_cancel_confirmed_on_a_later_read_is_still_crossed(self):
        """Alpaca answers a cancel with 204 and passes the order through `pending_cancel` (read as open):
        the House reads it again a moment later before it gives the cross up."""
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731

        def the_venue_finishes_the_cancel(seconds):
            self.slept.append(seconds)
            self.broker.orders[bid].status = "cancelled"

        with patch.object(self.broker, "cancel", side_effect=pending):
            self.book.sleep = the_venue_finishes_the_cancel
            out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        self.assertEqual(self.slept, [0.25])
        self.assertEqual(D(self.crossed_fills("buyer")[0]["quantity"]), held)
        self.assertTrue(self.book.reconcile().ok)

    def test_a_cancel_the_venue_refuses_leaves_the_exit_post_only_at_the_ask(self):
        held = self.hold("seller", self.inst, "1.62")
        self.rest_bid("buyer", self.inst, "3", "12.17")
        with patch.object(self.broker, "cancel", side_effect=BrokerError("gateway 502")):
            out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "resting", out.detail)
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.broker.submitted[-1].limit_price, D("12.19"))
        self.assertTrue(self.broker.submitted[-1].post_only)

    def test_a_fill_arriving_between_the_cancel_request_and_its_confirmation_is_booked_once(self):
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")

        def filled_in_flight(order_id):
            # The venue fills one coin of the bid as the cancel arrives, and answers the cancel with
            # the count it read before (the Kalshi adapter's `cancel` reads, then deletes).
            stale = copy.copy(self.broker.get_order(order_id))
            self.broker.fill_resting(bid, "1")
            self.broker.orders[bid].status = "cancelled"
            stale.status = "cancelled"
            return stale

        with patch.object(self.broker, "cancel", side_effect=filled_in_flight):
            out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        venue = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="buyer") if e.payload.get("source") == "venue"]
        self.assertEqual([D(v["quantity"]) for v in venue], [D("1")])  # the fill in flight, once
        (crossed,) = self.crossed_fills("buyer")
        self.assertEqual(D(crossed["quantity"]), held)  # 2 left unfilled, the exit needed 1.61...
        self.assertTrue(self.book.reconcile().ok)
        before = self.snapshot_state()
        self.book = self.new_book()
        self.book.poll()
        self.assertEqual(self.snapshot_state(), before)
        self.assertTrue(self.book.reconcile().ok)

    def test_a_cross_takes_only_what_the_venue_left_unfilled_of_the_bid(self):
        """Review of #226: the guard against a quantity filled twice -- a cross takes the bid's quantity LESS
        every venue fill booked -- was never exercised (in every test the exit was smaller than what the venue
        had left of the bid, so crossing the whole bid passed too). Here the venue fills 2 of a 3 bid while the
        House cancels it and the exit needs almost 3: 1 is crossed and the rest goes to the venue."""
        held = self.hold("seller", self.inst, "3")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")

        def filled_in_flight(order_id):
            stale = copy.copy(self.broker.get_order(order_id))
            self.broker.fill_resting(bid, "2")
            self.broker.orders[bid].status = "cancelled"
            stale.status = "cancelled"
            return stale

        with patch.object(self.broker, "cancel", side_effect=filled_in_flight):
            out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        venue = [D(e.payload["quantity"]) for e in self.ledger.iter(kinds="book.fill", agent="buyer") if e.payload.get("source") == "venue"]
        self.assertEqual(venue, [D("2")])
        (crossed,) = self.crossed_fills("buyer")
        self.assertEqual(D(crossed["quantity"]), D("1"))  # 3 bid, 2 filled at the venue: 1 left to cross, never 3
        self.assertEqual(self.broker.submitted[-1].quantity, held - D("1"))  # the rest of the exit, at the venue
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_a_later_slice_of_an_exit_is_never_crossed(self):
        """Review of #226: `_advance_plan` clears a later slice with `cross=False` and then sends the whole slice.
        Nothing pinned it: crossed there, a slice meeting a peer's bid at the touch was crossed AND sent (7.98
        LINK held, 11.97 sold)."""
        self.seat("seller", usd="200", position="200", order="75")
        for _ in range(2):
            self.assertEqual(self.book.submit([self.intent("seller", self.inst, "buy", "4")])[0].status, "filled")
        held = self.book.account("seller").holdings[self.inst.key].quantity
        submit, calls = self.broker.submit, []

        def second_slice_refused(order_intent):
            calls.append(order_intent)
            if len(calls) == 2:
                raise RejectedOrder("the venue refused this slice")
            return submit(order_intent)

        with patch.object(self.broker, "submit", side_effect=second_slice_refused):
            self.book.submit([self.intent("seller", self.inst, "sell", held)])  # over the cap: an exit plan
        bid = self.rest_bid("peer", self.inst, "5", "12.17")  # a bid at the touch arrives before the next slice
        self.clock.advance(60)
        self.book.poll()
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertTrue(self.book.orders[bid].open)
        sold = sum((D(e.payload["quantity"]) for e in self.ledger.iter(kinds="book.fill", agent="seller")
                    if e.payload.get("source") == "venue" and e.payload["side"] == "sell"), D(0))
        offered = sum((w.remaining for w in self.book.open_orders("seller") if w.side == "sell"), D(0))
        self.assertLessEqual(sold + offered, held)
        self.assertEqual(self.broker.submitted[-1].limit_price, D("12.18"))  # one step above the House's bid

    def test_a_sliced_exit_keeps_the_agents_own_order_not_the_first_slices_floor(self):
        """Review of #226: an exit over the cap that D3 re-priced was started as a plan whose intent WAS the
        House's re-price (a limit at 12.11, one step above a peer's bid at 12.10). Once that bid was gone and the
        market had fallen to 11.90, the next slice of the agent's MARKET exit still went out at 12.11 and rested
        for the plan's hour. The plan keeps the agent's own order; each slice is cleared as it goes."""
        self.broker.set_quote(self.inst, "12.18", "12.19")
        self.seat("seller", usd="200", position="200", order="75")
        for _ in range(2):
            self.assertEqual(self.book.submit([self.intent("seller", self.inst, "buy", "4")])[0].status, "filled")
        held = self.book.account("seller").holdings[self.inst.key].quantity
        bid = self.rest_bid("peer", self.inst, "1", "12.10")  # under the touch: the exit is floored above it
        submit, calls = self.broker.submit, []

        def second_slice_refused(order_intent):
            calls.append(order_intent)
            if len(calls) == 2:
                raise RejectedOrder("the venue refused this slice")
            return submit(order_intent)

        with patch.object(self.broker, "submit", side_effect=second_slice_refused):
            self.book.submit([self.intent("seller", self.inst, "sell", held)])
        (plan,) = self.book.exit_plans.values()
        self.assertEqual((plan.intent.order_type, plan.intent.limit_price), ("market", None))  # the agent's own order
        for sliced in calls:  # both slices of the first pass: floored one step above the peer's bid
            self.assertEqual((sliced.order_type, sliced.limit_price), ("limit", D("12.11")))
        self.book.cancel("peer", bid)  # the House's bid goes away
        self.broker.set_quote(self.inst, "11.90", "11.92")  # and the market falls under the old floor
        self.clock.advance(60)
        self.book.poll()
        last = self.broker.submitted[-1]
        self.assertEqual((last.side, last.order_type, last.limit_price), ("sell", "market", None))
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_a_bid_that_filled_before_the_exit_is_booked_and_not_crossed(self):
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        self.broker.fill_resting(bid, "3")  # filled at the venue since the book last asked
        out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertEqual(self.broker.cancelled, [])
        self.assertEqual(self.crossed_fills("buyer"), [])
        self.assertEqual(self.book.orders[bid].status, "filled")
        self.assertEqual(self.broker.submitted[-1].order_type, "market")
        self.assertTrue(self.book.reconcile().ok)

    def test_a_limit_exit_through_a_peers_bid_crosses_at_the_bids_better_price(self):
        """haghani-56's limit sell of AVAX at 10.2704 under haghani-39's bid at 10.3048 (Sept 23 16:16Z)."""
        held = self.hold("seller", self.inst, "1.62")
        self.rest_bid("buyer", self.inst, "3", "12.17")
        out = self.book.submit([self.intent("seller", self.inst, "sell", held, order_type="limit", limit_price="12.10")])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        self.assertEqual(D(self.crossed_fills("seller")[0]["price"]), D("12.17"))

    def test_a_take_profit_above_the_ask_is_never_re_priced_under_its_limit(self):
        """Review of #226: a market order of the House's still in flight stands in the way of EVERY sell
        (its price is unknown), so a take-profit limit sell above the ask went down the doubt path and was
        re-priced post-only to the ask, 12.19, under the 12.50 its holder asked for."""
        held = self.hold("seller", self.inst, "1.62")
        self.broker.asynchronous = True  # Alpaca accepts a market order first and fills it a moment later
        self.seat("buyer")
        self.assertEqual(self.book.submit([self.intent("buyer", self.inst, "buy", "1")])[0].status, "sent")
        out = self.book.submit([self.intent("seller", self.inst, "sell", held, order_type="limit", limit_price="12.50")])[0]
        self.assertEqual(out.status, "resting", out.detail)
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("12.50"), True))
        self.assertIn("post-only limit at your own limit 12.50", out.detail)

    def test_nothing_is_crossed_while_the_venue_is_shut(self):
        """Review of #226: outside the regular session only a LIMIT exit of a stock passes `check`; it met a
        peer's resting bid and the two were crossed at once, on the close's quote -- a fill the venue could not
        have made until the open. It goes to the venue one cent above the House's bid instead, to wait."""
        spy = Instrument("equity", "SPY", self.venue)
        self.broker.set_quote(spy, "50.00", "50.02")
        held = self.hold("seller", spy, "1")
        bid = self.rest_bid("buyer", spy, "1", "50.00")
        self.book.market_open = lambda instrument, now: False if instrument.asset_class in ("equity", "option") else None
        out = self.book.submit([self.intent("seller", spy, "sell", held, order_type="limit", limit_price="49.90")])[0]
        self.assertEqual(out.status, "resting", out.detail)
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(self.book.orders[bid].open)
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price), ("sell", "limit", D("50.01")))

    def test_an_entry_that_would_cross_is_still_refused(self):
        self.hold("seller", self.inst, "3")
        self.seat("buyer")
        ask = self.book.submit([self.intent("seller", self.inst, "sell", "1", order_type="limit", limit_price="12.20")])[0]
        self.assertEqual(ask.status, "resting")
        market = self.book.submit([self.intent("buyer", self.inst, "buy", "1")])[0]
        self.assertEqual(market.status, "refused")
        self.assertIn("a market order here could trade against the House's own resting order", market.detail)
        limit = self.book.submit([self.intent("buyer", self.inst, "buy", "1", order_type="limit", limit_price="12.20")])[0]
        self.assertEqual(limit.status, "refused")
        self.assertIn("this price would trade against the House's own resting order", limit.detail)
        self.assertEqual(self.broker.cancelled, [])

    def test_a_frozen_book_never_crosses(self):
        held = self.hold("seller", self.inst, "1.62")
        self.rest_bid("buyer", self.inst, "3", "12.17")
        self.book.frozen = "cash differs by 1.0000"
        out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.broker.cancelled, [])
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("12.18"), False))
        self.assertIn("one step above the House's own resting bid", out.detail)

    def fallback_exit(self, held, bid_quantity="3"):
        """The doubt path of the review of #226: a peer's bid at the touch, whose cancel the venue has not confirmed
        after two re-reads (Alpaca's pending_cancel), so the time stop rests post-only at the ask, 12.19."""
        bid = self.rest_bid("buyer", self.inst, bid_quantity, "12.17")
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731
        with patch.object(self.broker, "cancel", side_effect=pending):
            first = self.book.submit([self.intent("seller", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual(first.status, "resting", first.detail)
        self.assertEqual((self.broker.submitted[-1].limit_price, self.broker.submitted[-1].post_only), (D("12.19"), True))
        return bid, self.book.orders[first.order_id]

    def test_a_time_stop_in_a_falling_market_supersedes_the_houses_fallback_and_gets_out(self):
        """Review of #226 (owner's decision): the House's post-only fallback held the units, so the agent's next time
        stop was refused ("sell exceeds position") while the market fell through it. The agent's own next sell now
        cancels the House's re-priced exit first and is checked as if it were gone."""
        held = self.hold("seller", self.inst, "1.62")
        bid, fallback = self.fallback_exit(held)
        self.broker.orders[bid].status = "cancelled"  # the venue finishes the House's cancel of the peer's bid
        self.broker.set_quote(self.inst, "12.00", "12.02")  # and the market falls
        again = self.book.submit([self.intent("seller", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual(again.status, "filled", again.detail)
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertEqual(fallback.status, "cancelled")
        told = [r for r in order_outcomes(self.ledger, "seller", self.book.name) if r.get("order_id") == fallback.order_id][-1]
        self.assertIn("your newer sell of this instrument replaces this exit", told["reason"])
        sold = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="seller") if e.payload["side"] == "sell"]
        self.assertEqual([(p["source"], D(p["price"])) for p in sold], [("venue", D("12.00"))])
        self.assertTrue(self.book.reconcile().ok)

    def test_the_houses_fallback_is_sent_again_as_asked_at_the_next_pass_once_nothing_is_in_the_way(self):
        """Review of #226 (owner's decision): the fallback lives one pass. Here the peer's bid is gone and the market
        has fallen; with no new intent, and across a restart, the next poll cancels the resting fallback and sends
        the agent's own market sell again, which gets out at the new bid."""
        held = self.hold("seller", self.inst, "1.62")
        bid, fallback = self.fallback_exit(held)
        self.broker.orders[bid].status = "cancelled"
        self.broker.set_quote(self.inst, "12.00", "12.02")
        seats = dict(self.book.limits)
        self.book = self.new_book()  # a restart: the order rows alone say the fallback was the House's re-price
        self.book.limits.update(seats)
        self.book.reconcile()
        self.book.poll()
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertEqual(self.book.orders[fallback.order_id].status, "cancelled")
        told = [r for r in order_outcomes(self.ledger, "seller", self.book.name) if r.get("order_id") == fallback.order_id][-1]
        self.assertIn("to send your exit again", told["reason"])
        again = self.broker.submitted[-1]
        self.assertEqual((again.side, again.order_type, again.quantity), ("sell", "market", held))
        self.assertNotEqual(f"ord-{again.id[3:]}", fallback.order_id)  # its own client order id
        sold = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="seller") if e.payload["side"] == "sell"]
        self.assertEqual([(p["source"], D(p["price"]), p["intent_id"]) for p in sold],
                         [("venue", D("12.00"), fallback.shares[0].intent_id)])  # the same intent, filled once
        self.assertTrue(self.book.reconcile().ok)

    def test_while_the_doubt_stands_the_fallback_follows_the_ask_and_does_not_churn(self):
        """Review of #226 (owner's decision): while the House's order in the way is still in doubt (a peer's bid the
        venue has not acknowledged), the next pass re-prices the fallback to the NEW ask; a pass that finds nothing
        changed leaves it where it is."""
        held = self.hold("seller", self.inst, "1.62")
        self.seat("buyer")
        self.broker.lose_next_submit = True  # the peer's bid is `unknown`: in doubt until the venue says where it stands
        self.assertEqual(self.book.submit([self.intent("buyer", self.inst, "buy", "3", order_type="limit",
                                                       limit_price="12.00")])[0].status, "unknown")
        first = self.book.submit([self.intent("seller", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual((self.broker.submitted[-1].limit_price, self.broker.submitted[-1].post_only), (D("12.19"), True))
        self.broker.set_quote(self.inst, "12.08", "12.10")
        self.clock.advance(30)
        self.book.poll()
        self.assertEqual(self.book.orders[first.order_id].status, "cancelled")
        moved = self.broker.submitted[-1]
        self.assertEqual((moved.side, moved.order_type, moved.limit_price, moved.post_only), ("sell", "limit", D("12.10"), True))
        sent = len(self.broker.submitted)
        self.clock.advance(10)
        self.book.poll()
        self.assertEqual(len(self.broker.submitted), sent)  # nothing changed: nothing cancelled or sent again
        self.assertEqual(self.book.account("seller").holdings[self.inst.key].quantity, held)  # still offered once, never twice

    def test_a_supersede_the_venue_has_not_confirmed_never_sells_the_units_twice(self):
        held = self.hold("seller", self.inst, "1.62")
        bid, fallback = self.fallback_exit(held)
        pending = lambda order_id: self.broker.get_order(order_id)  # noqa: E731 - the fallback's cancel stays pending
        with patch.object(self.broker, "cancel", side_effect=pending):
            again = self.book.submit([self.intent("seller", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual(again.status, "refused", again.detail)  # its units are still offered by the fallback
        self.assertTrue(fallback.open)
        offered = sum((w.remaining for w in self.book.open_orders("seller") if w.side == "sell"), D(0))
        self.assertEqual(offered, held)  # offered once, never twice

    def test_without_a_fresh_market_bid_nothing_is_crossed(self):
        """Review of #226 (owner's decision): a cross pays the seller the market's bid, so a quote older than the book
        lets a quote be (`max_quote_age_seconds`, 900 s) prices no cross: the exit takes the doubt path and rests
        post-only at the ask, and the peer's bid is left alone."""
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        self.clock.advance(901)  # the venue's quote (stamped at the start) is now 901 s old
        out = self.book.submit([self.intent("seller", self.inst, "sell", held)])[0]
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(self.book.orders[bid].open)
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("12.19"), True))
        self.assertIn("no fresh market bid", out.detail)

    def test_a_kill_switch_engaged_while_the_way_is_cleared_stops_the_cross(self):
        """Review of #226 (mutation testing): the kill-switch guard in `_crossable` could be removed with every test
        passing, because `check` refuses everything while the switch is on. It still decides one case: the switch
        engaged after `check` read it, while the House clears the way at the venue. A cross fills the bidder's
        ENTRY, which an engaged switch forbids, so none is booked."""
        held = self.hold("seller", self.inst, "1.62")
        bid = self.rest_bid("buyer", self.inst, "3", "12.17")
        reads = iter([False])  # `check` reads it off; the owner engages it a moment later
        self.book.kill_switch = lambda: next(reads, True)
        self.book.submit([self.intent("seller", self.inst, "sell", held)])
        self.assertEqual(self.crossed_fills("seller"), [])
        self.assertEqual(self.crossed_fills("buyer"), [])
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(self.book.orders[bid].open)

    def test_bids_under_the_market_are_left_alone_and_the_exit_takes_the_markets_bid(self):
        """The snapshot's five bids under a market bidding 12.18: a sell at the venue fills there and
        never reaches them, so none is cancelled and the exit goes out floored one step above the
        best of them (the House's bids were 1.3-3% under their means; crossing one at its limit would
        have filled its bidder at a price the market never reached)."""
        held = self.hold("haghani-hb85bb8", self.inst, "1.62")
        self.broker.set_quote(self.inst, "12.18", "12.19")
        orders = self.snapshot_bids()
        out = self.book.submit([self.intent("haghani-hb85bb8", self.inst, "sell", held, reason=EXIT_REASON)])[0]
        self.assertEqual(out.status, "filled", out.detail)  # was "refused"
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(all(self.book.orders[order_id].open for order_id in orders.values()))
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("12.173015626"), False))
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="haghani-hb85bb8")][-1]
        self.assertEqual((fill["source"], D(fill["price"])), ("venue", D("12.18")))  # the market's bid, not the House's
        self.assertEqual(self.crossed_fills("haghani-hb85bb8"), [])
        told = order_outcomes(self.ledger, "haghani-hb85bb8", self.book.name)[-1]
        self.assertEqual(told["status"], "filled")
        self.assertTrue(self.book.reconcile().ok)


class RealAlpacaExitTest(PracticeAlpacaExitTest):
    venue, family, real, cash = "alpaca", "alpaca", True, "5000"


class RealKalshiExitTest(CrossCase):
    """A NO holder's exit meets a peer's resting NO bid: in YES space the sell is a YES buy."""

    venue, family, real, cash = "kalshi", "kalshi", True, "500"

    def setUp(self):
        super().setUp()
        self.no = event("no", venue=self.venue)
        self.broker.set_quote(self.no, "0.40", "0.42")
        self.broker.set_quote(event("yes", venue=self.venue), "0.58", "0.60")

    def test_a_no_exit_crosses_a_peers_resting_no_bid(self):
        held = self.hold("seller", self.no, "5")
        bid = self.rest_bid("buyer", self.no, "10", "0.40", post_only=True)
        out = self.book.submit([self.intent("seller", self.no, "sell", held)])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        self.assertEqual(self.broker.cancelled, [bid])
        taker = Fees("kalshi").charge(self.no, "sell", held, D("0.40"), liquidity="taker")
        maker = Fees("kalshi").charge(self.no, "buy", held, D("0.40"), liquidity="maker")
        (sold,) = self.crossed_fills("seller")
        (bought,) = self.crossed_fills("buyer")
        self.assertEqual(D(sold["fee_usd"]), taker.usd)
        self.assertEqual(D(bought["fee_usd"]), maker.usd)
        self.assertEqual(self.book.account("buyer").holdings[self.no.key].quantity, D("5"))
        self.assertEqual(self.book.account("seller").holdings, {})
        self.assertEqual(self.book.open_orders("buyer"), [])  # the other five are not re-placed
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(self.book.frozen)

    def test_a_bid_inside_the_spread_pays_the_seller_only_the_markets_bid(self):
        """Review of #226 (owner's decision): the House's own post-only re-pricing rests bids one tick under the
        ask, inside the spread. A market NO exit crossed with such a bid at 0.42 was paid 0.42 where its venue would
        have paid it 0.40, the market's bid. The seller now gets 0.40, the bidder still pays its 0.42 limit, and the
        House row keeps the two cents a contract."""
        self.broker.set_quote(self.no, "0.40", "0.43")
        self.broker.set_quote(event("yes", venue=self.venue), "0.57", "0.60")
        held = self.hold("seller", self.no, "5")
        self.rest_bid("buyer", self.no, "5", "0.42", post_only=True)
        house_before = self.book.account(HOUSE).cash
        out = self.book.submit([self.intent("seller", self.no, "sell", held)])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        (sold,) = self.crossed_fills("seller")
        (bought,) = self.crossed_fills("buyer")
        self.assertEqual(D(sold["price"]), D("0.40"))
        self.assertEqual(D(bought["price"]), D("0.42"))
        taker = Fees("kalshi").charge(self.no, "sell", held, D("0.40"), liquidity="taker")
        maker = Fees("kalshi").charge(self.no, "buy", held, D("0.42"), liquidity="maker")
        self.assertEqual(self.book.account(HOUSE).cash - house_before, q_cash(held * D("0.02") + taker.usd + maker.usd))
        self.assertTrue(self.book.reconcile().ok)

    def test_a_crossed_limit_exit_is_never_paid_under_its_own_limit(self):
        self.broker.set_quote(self.no, "0.40", "0.43")
        self.broker.set_quote(event("yes", venue=self.venue), "0.57", "0.60")
        held = self.hold("seller", self.no, "5")
        self.rest_bid("buyer", self.no, "5", "0.42", post_only=True)
        out = self.book.submit([self.intent("seller", self.no, "sell", held, order_type="limit", limit_price="0.41")])[0]
        self.assertEqual(out.status, "crossed", out.detail)
        self.assertEqual(D(self.crossed_fills("seller")[0]["price"]), D("0.41"))  # its own limit, over the 0.40 bid
        self.assertEqual(D(self.crossed_fills("buyer")[0]["price"]), D("0.42"))
        self.assertTrue(self.book.reconcile().ok)

    def test_a_no_bid_under_the_market_is_left_and_the_exit_goes_one_cent_above_it(self):
        held = self.hold("seller", self.no, "5")
        bid = self.rest_bid("buyer", self.no, "10", "0.38", post_only=True)
        out = self.book.submit([self.intent("seller", self.no, "sell", held)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(self.book.orders[bid].open)
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price), ("sell", "limit", D("0.39")))
        self.assertTrue(self.book.reconcile().ok)

    def test_a_post_only_exit_is_never_crossed_as_a_taker(self):
        """A post-only sell asked never to take: through the House's bid it rests one cent above it,
        still post-only, and the bid is left alone."""
        held = self.hold("seller", self.no, "5")
        bid = self.rest_bid("buyer", self.no, "10", "0.40", post_only=True)
        out = self.book.submit([self.intent("seller", self.no, "sell", held, order_type="limit", limit_price="0.40", post_only=True)])[0]
        self.assertEqual(out.status, "resting", out.detail)
        self.assertEqual(self.broker.cancelled, [])
        self.assertTrue(self.book.orders[bid].open)
        self.assertEqual(self.crossed_fills("seller"), [])
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("0.41"), True))

    def test_a_no_take_profit_is_never_re_priced_under_its_limit(self):
        """Review of #226: a market buy whose answer was lost stays `unknown` (open, unpriced) and stands in
        the way of every sell of the market; a NO take-profit at 0.55 was re-priced to the NO ask, 0.42."""
        held = self.hold("seller", self.no, "5")
        self.seat("buyer")
        self.broker.lose_next_submit = True
        self.assertEqual(self.book.submit([self.intent("buyer", self.no, "buy", "2")])[0].status, "unknown")
        out = self.book.submit([self.intent("seller", self.no, "sell", held, order_type="limit", limit_price="0.55")])[0]
        self.assertEqual(out.status, "resting", out.detail)
        sent = self.broker.submitted[-1]
        self.assertEqual((sent.side, sent.order_type, sent.limit_price, sent.post_only), ("sell", "limit", D("0.55"), True))

    def test_a_sell_with_no_price_left_is_not_refused_as_a_self_cross(self):
        """Review of #226: docs/operations.md calls a sell refused for "the House's own resting order" a D3
        defect. Where no price exists at all -- a House bid at 0.99 on a stale quote while a cross is not
        allowed (a frozen book) -- the sell is refused, but in words that are not the old self-cross refusal."""
        yes = event("yes", venue=self.venue)
        self.broker.set_quote(yes, "0.97", "0.98")
        held = self.hold("seller", yes, "3")
        self.broker.set_quote(yes, "0.98", "1.00")
        self.rest_bid("buyer", yes, "5", "0.99", post_only=True)
        self.broker.set_quote(yes, "0.98", "0.99")  # a stale ask at the House's own bid
        self.book.frozen = "cash differs by 1.0000"  # a frozen book never crosses: it would fill the bidder's entry
        out = self.book.submit([self.intent("seller", yes, "sell", held)])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("no price is left above the House's own best bid", out.detail)
        refused = [r for e in self.ledger.iter(kinds="book.refused", agent="seller") for r in e.payload["reasons"]]
        self.assertTrue(refused)
        self.assertFalse(any("House's own resting order" in reason for reason in refused), refused)

    def test_an_entry_on_the_other_side_is_still_refused(self):
        self.hold("seller", self.no, "5")
        self.book.submit([self.intent("seller", self.no, "sell", "5", order_type="limit", limit_price="0.45")])
        self.seat("buyer")
        out = self.book.submit([self.intent("buyer", self.no, "buy", "5", order_type="limit", limit_price="0.45", post_only=True)])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("own resting order", out.detail)


class PracticeKalshiExitTest(RealKalshiExitTest):
    venue, family, real, cash = "kalshi-shadow", "kalshi", False, "100000"


class ExitCrossRecoveryTest(unittest.TestCase):
    """A resting cross is committed as one `book.cross_plan`: a restart, or the next submit or poll,
    finishes it from the ledger alone, with no quote and no venue call, at every boundary."""

    def scenario(self, *, boundary=None, after=False, resume="restart", lost_ack=False):
        case = PracticeAlpacaExitTest()
        case.setUp()
        try:
            held = case.hold("seller", case.inst, "1.62")
            bid = case.rest_bid("buyer", case.inst, "3", "12.17")
            exit_intent = case.intent("seller", case.inst, "sell", held)
            original = case.book._apply
            writes = 0

            def interrupted(kind, agent, payload, at):
                nonlocal writes
                crossing = kind == "book.cross_plan" or (kind == "book.fill" and payload.get("source") in ("cross", "cross-house"))
                if crossing:
                    writes += 1
                    if writes == boundary and not after:
                        raise RuntimeError("stopped before applying a committed cross row")
                result = original(kind, agent, payload, at)
                if crossing and writes == boundary and after:
                    raise RuntimeError("stopped after applying a committed cross row")
                return result

            if lost_ack:
                append_many = case.ledger.append_many

                def lost(rows):
                    entries = append_many(rows)
                    if any(entry.kind == "book.cross_plan" for entry in entries):
                        raise RuntimeError("committed, acknowledgement lost")
                    return entries

                with patch.object(case.ledger, "append_many", side_effect=lost), self.assertRaises(RuntimeError):
                    case.book.submit([exit_intent])
            elif boundary is None:
                case.book.submit([exit_intent])
            else:
                with patch.object(case.book, "_apply", side_effect=interrupted), self.assertRaises(RuntimeError):
                    case.book.submit([exit_intent])
            submitted = len(case.broker.submitted)
            with patch.object(case.broker, "quote", side_effect=AssertionError("recovery must not requote")), \
                    patch.object(case.broker, "submit", side_effect=AssertionError("recovery must not trade")), \
                    patch.object(case.broker, "cancel", side_effect=AssertionError("recovery must not cancel again")):
                if resume == "restart":
                    case.book = case.new_book()
                elif resume == "submit":
                    self.assertEqual(case.book.submit([]), [])
                else:
                    case.book.poll()
                again = case.new_book()
            self.assertEqual(len(case.broker.submitted), submitted)
            self.assertFalse(case.book._cross_plans)
            self.assertFalse(case.book.orders[bid].open)
            self.assertTrue(case.book.reconcile().ok)
            self.assertTrue(again.reconcile().ok)
            self.assertEqual(case.ledger.count(kinds="book.cross_plan"), 2)
            case.ledger.verify()
            return case.snapshot_state(), [(e.id, e.payload) for e in case.ledger.iter(kinds="book.fill")
                                           if e.payload.get("source") in ("cross", "cross-house")]
        finally:
            case.tearDown()

    def test_every_boundary_recovers_to_the_uninterrupted_book(self):
        expected = self.scenario()
        for after in (False, True):
            for boundary in range(1, 7):  # plan, seller, seller's House row, buyer, buyer's House row, completion
                with self.subTest(boundary=boundary, after=after):
                    self.assertEqual(self.scenario(boundary=boundary, after=after), expected)

    def test_poll_or_intake_finishes_it_without_a_restart(self):
        expected = self.scenario()
        for resume in ("poll", "submit"):
            with self.subTest(resume=resume):
                self.assertEqual(self.scenario(boundary=3, resume=resume), expected)
                self.assertEqual(self.scenario(lost_ack=True, resume=resume), expected)

    def test_a_crash_before_the_cross_is_committed_leaves_no_fill_and_a_balanced_book(self):
        case = PracticeAlpacaExitTest()
        case.setUp()
        try:
            held = case.hold("seller", case.inst, "1.62")
            bid = case.rest_bid("buyer", case.inst, "3", "12.17")
            with patch.object(case.book, "_commit_cross", side_effect=RuntimeError("the process stopped")), \
                    self.assertRaises(RuntimeError):
                case.book.submit([case.intent("seller", case.inst, "sell", held)])
            seats = dict(case.book.limits)  # the House seats agents on a restarted book; the ledger holds no seat
            case.book = case.new_book()
            case.book.limits.update(seats)
            self.assertEqual(case.ledger.count(kinds="book.cross_plan"), 0)
            self.assertEqual(case.book.orders[bid].status, "cancelled")  # the venue did cancel it
            self.assertEqual(case.book.account("seller").holdings[case.inst.key].quantity, held)  # still held: it asks again
            self.assertEqual(case.book.account("buyer").holdings, {})
            self.assertTrue(case.book.reconcile().ok)
            # The agent's next wake sells with a fresh intent; no bid is left to cross, so it goes to the venue.
            out = case.book.submit([case.intent("seller", case.inst, "sell", held)])[0]
            self.assertEqual(out.status, "filled", out.detail)
            self.assertTrue(case.book.reconcile().ok)
        finally:
            case.tearDown()


class StaleCancelAnswerTest(CrossCase):
    """`Book.cancel` books what the venue says AFTER the cancel, not the cancel's own answer: the Kalshi
    adapter reads an order, then deletes it, and returns the count it read before the delete, so a fill
    in between was closed as "cancelled" without it and never polled again (found building D3)."""

    venue, family, real, cash = "kalshi", "kalshi", True, "500"

    def test_a_fill_in_the_cancels_window_is_booked(self):
        inst = event("yes", venue=self.venue)
        self.broker.set_quote(inst, "0.58", "0.60")
        bid = self.rest_bid("a1", inst, "10", "0.57", post_only=True)

        def read_then_delete(order_id):
            stale = copy.copy(self.broker.get_order(order_id))
            self.broker.fill_resting(bid, "4")
            self.broker.orders[bid].status = "cancelled"
            stale.status = "cancelled"
            return stale

        with patch.object(self.broker, "cancel", side_effect=read_then_delete):
            out = self.book.cancel("a1", bid)
        self.assertEqual(out.status, "cancelled")
        self.assertEqual(out.filled, D("4"))
        self.assertEqual(self.book.account("a1").holdings[inst.key].quantity, D("4"))
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)


class EventOfTickerTest(unittest.TestCase):
    """Pinned with the A-money builder's `event_key` (Sept 24, 2026), `league/tapes.py` and Kalshi's own
    `event_ticker`: a Kalshi market's event is its ticker's first two `-` segments, and a ticker of fewer
    than three segments is its own event."""

    def test_the_event_is_the_tickers_first_two_segments(self):
        from league.book import _event_of

        for ticker, event_ticker in (
            ("KXMLBTOTAL-26SEP231840MILPHI-6", "KXMLBTOTAL-26SEP231840MILPHI"),
            ("KXMLBTOTAL-26SEP231835TORBALG2-10", "KXMLBTOTAL-26SEP231835TORBALG2"),
            ("KXBTCD-26SEP2401-T62999.99", "KXBTCD-26SEP2401"),
            ("KXHIGHNY-26SEP22-B75.5", "KXHIGHNY-26SEP22"),
            # Review of #226: a player prop is its GAME's (Kalshi's recorded event_ticker for
            # KXMLBHIT-26AUG311940MILCHC-CHCPCROWARMSTRONG4-1 is KXMLBHIT-26AUG311940MILCHC); 109 such
            # tickers traded on the shadow book by T0. Dropping the last segment made each player an event.
            ("KXMLBHIT-26SEP222140LAAATH-LAAMTROUT27-4", "KXMLBHIT-26SEP222140LAAATH"),
            ("KXMLBHR-26SEP191840CHCCIN-CINKHAYES3-1", "KXMLBHR-26SEP191840CHCCIN"),
            ("KXT20MATCH-26SEP230900GHANGA-A-NGA-A", "KXT20MATCH-26SEP230900GHANGA"),
            # ... and a two-segment market is its own event (Kalshi: event_ticker == ticker), never its series.
            ("KXMLBRFI-26SEP151940ATLCHC", "KXMLBRFI-26SEP151940ATLCHC"),
            ("KXHMONTH-26AUG", "KXHMONTH-26AUG"),
        ):
            with self.subTest(ticker=ticker):
                self.assertEqual(_event_of(ticker), event_ticker)
                self.assertEqual(_event_of(ticker.lower()), event_ticker)


if __name__ == "__main__":
    unittest.main()

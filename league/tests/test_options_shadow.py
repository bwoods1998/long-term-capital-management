"""The options shadow account (Sept 25, 2026, the options-desk run's Track S): every level-3 structure on
practice, held as one position, filled on live leg quotes under rules that never flatter.

Pins the broker's surface and its fill rules (a newer quote than the decision's, at the touch, within
the limit, 10% of each leg's shown size over its ratio, the session, day orders), its fee to the cent
against the book's own model, its marks, its state across a restart, the expiry safety net, and the
whole path through `Book`: a structure bought, marked, sold flat as ONE closed trade, reconciled after
every step and after a restart.
"""

import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ltcm.broker import Broker, BrokerError, Instrument, OrderIntent, RejectedOrder, VenueUnavailable

from league import structures
from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import Ledger, now_iso
from league.options_shadow import OptionsShadowBroker, alpaca_leg_quotes, alpaca_underlying_close, stamp
from league.structures import classify
from league.tests.fakes import Clock
from league.venues import instrument_for, market_hours

D = Decimal
V = "options-shadow"


def epoch(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


#: Friday Sept 25, 2026, 10:00 New York: inside the regular session.
FRIDAY_10 = epoch("2026-09-25T14:00:00Z")


def occ(strike, right="C", expiry="260928", root="SPY"):
    return f"{root}{expiry}{right}{int(D(str(strike)) * 1000):08d}"


def spec(type_, *legs):
    """legs: (strike, role, right, expiry, ratio)"""
    parsed = []
    for strike, role, right, expiry, ratio in legs:
        parsed.append(structures.Leg(instrument_for(V, {"occ": occ(strike, right, expiry)}), 1 if role == "long" else -1, ratio))
    return classify(type_, parsed)


VERTICAL = spec("debit_vertical", (580, "long", "C", "260928", 1), (581, "short", "C", "260928", 1))
CONDOR = spec("iron_condor", (575, "long", "P", "260928", 1), (576, "short", "P", "260928", 1),
              (585, "short", "C", "260928", 1), (586, "long", "C", "260928", 1))
CALENDAR = spec("calendar", (580, "short", "C", "260928", 1), (580, "long", "C", "261002", 1))
BUTTERFLY = spec("long_butterfly", (579, "long", "C", "260928", 1), (580, "short", "C", "260928", 2), (581, "long", "C", "260928", 1))


class Legs:
    """The leg source by script: a bid, an ask, their sizes and the quote's time per OCC symbol."""

    def __init__(self, clock):
        self.clock = clock
        self.rows = {}
        self.calls = []
        self.down = False

    def set(self, symbol, bid, ask, *, bid_size="100", ask_size="100", at=None):
        self.rows[symbol] = {"bid": None if bid is None else D(bid), "ask": None if ask is None else D(ask),
                             "bid_size": None if bid_size is None else D(bid_size), "ask_size": None if ask_size is None else D(ask_size),
                             "as_of": at or stamp(now_iso(self.clock))}

    def touch(self, symbol):
        """The leg quoted again now, as it was (a newer quote of the same prices)."""
        row = self.rows[symbol]
        row["as_of"] = stamp(now_iso(self.clock))

    def __call__(self, symbols):
        self.calls.append(sorted(symbols))
        if self.down:
            raise RuntimeError("the source is down")
        return {s: dict(self.rows[s]) for s in symbols if s in self.rows}


class Closes:
    def __init__(self):
        self.prices = {}
        self.calls = []

    def __call__(self, symbol, day):
        self.calls.append((symbol, day))
        return self.prices.get((symbol, day))


class ShadowCase(unittest.TestCase):
    cash = "10000"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "state" / "options-shadow.json"
        self.clock = Clock(FRIDAY_10)
        self.legs = Legs(self.clock)
        self.closes = Closes()
        self.quote_vertical()
        self.broker = self.new_broker()
        self.n = 0

    def new_broker(self, **kw):
        return OptionsShadowBroker(self.path, self.legs, underlying_close=self.closes, starting_cash=kw.pop("starting_cash", self.cash),
                                   clock=self.clock, **kw)

    # The vertical 580/581 call: bid 1.50 - 1.04 = 0.46, ask 1.55 - 1.00 = 0.55.
    def quote_vertical(self, low=("1.50", "1.55"), high=("1.00", "1.04"), **sizes):
        self.legs.set(occ(580), *low, **sizes)
        self.legs.set(occ(581), *high, **sizes)

    # The condor 575/576 puts, 585/586 calls, K = 1: ask 1 + .22 + .20 - .35 - .30 = 0.77, bid 1 + .20 + .18 - .37 - .32 = 0.69.
    def quote_condor(self):
        self.legs.set(occ(575, "P"), "0.20", "0.22")
        self.legs.set(occ(576, "P"), "0.35", "0.37")
        self.legs.set(occ(585), "0.30", "0.32")
        self.legs.set(occ(586), "0.18", "0.20")

    def later(self, seconds=30):
        self.clock.advance(seconds)

    def intent(self, spec_, side, quantity, limit, **kw):
        self.n += 1
        return OrderIntent.new(
            desk_id="book-options-shadow", instrument=kw.pop("instrument", None) or structures.instrument(spec_, V), side=side,
            quantity=quantity, order_type=kw.pop("order_type", "limit"), limit_price=limit, time_in_force=kw.pop("time_in_force", "day"),
            rationale="test", created_at=now_iso(self.clock), nonce=kw.pop("nonce", str(self.n)),
            **({"purpose": "exit", "exit_reason": "desk", "exit_of": "x"} if side == "sell" else {}), **kw,
        )

    def buy(self, spec_, quantity, limit, **kw):
        return self.broker.submit(self.intent(spec_, "buy", quantity, limit, **kw))

    def sell(self, spec_, quantity, limit, **kw):
        return self.broker.submit(self.intent(spec_, "sell", quantity, limit, **kw))

    def held(self):
        return {p.instrument.market_id: p.quantity for p in self.broker.positions()}

    def cash_now(self):
        return self.broker.balance().cash

    def own(self, spec_, quantity, price="0.55"):
        """Hold `quantity` of the vertical, bought at the ask 0.55 on a newer quote."""
        self.buy(spec_, quantity, price)
        self.later()
        for symbol in list(self.legs.rows):
            self.legs.touch(symbol)
        self.broker.advance()
        self.later()


class Surface(ShadowCase):
    def test_it_is_a_broker_of_structures_that_says_it_is_a_shadow(self):
        self.assertIsInstance(self.broker, Broker)
        self.assertEqual(self.broker.venue, V)
        self.assertEqual(self.broker.capabilities(), {"option", "limit", "structures", "shadow"})
        balance = self.broker.balance()
        self.assertEqual((balance.cash, balance.equity, balance.buying_power), (D(10000), D(10000), D(10000)))
        self.assertEqual((self.broker.positions(), self.broker.open_orders(), self.broker.fills()), ([], [], []))

    def test_what_is_not_a_structure_or_not_a_structure_order_is_refused_and_leaves_no_order(self):
        single = instrument_for(V, {"occ": occ(580)})
        bad = [
            self.intent(VERTICAL, "buy", "1", "0.55", instrument=single),  # a single contract
            self.intent(VERTICAL, "buy", "1", "10", instrument=Instrument("equity", "SPY", V)),
            self.intent(VERTICAL, "buy", "1", "0.55", instrument=structures.instrument(VERTICAL, "alpaca-paper")),
            self.intent(VERTICAL, "buy", "1", None, order_type="market"),
            self.intent(VERTICAL, "buy", "1", "0.55", time_in_force="gtc"),
            self.intent(VERTICAL, "buy", "1.5", "0.55"),
            self.intent(VERTICAL, "buy", "1", "0.555"),
        ]
        tampered = structures.instrument(VERTICAL, V)
        # A reversed code (the long leg the cheaper strike: a credit vertical named a debit one) is never traded.
        bad.append(self.intent(VERTICAL, "buy", "1", "0.55", instrument=Instrument(
            "option", "SPY", V, multiplier=100, expiry=tampered.expiry, strike=tampered.strike, right="call",
            market_id=f"debit_vertical|-1{occ(580)}|+1{occ(581)}")))
        for intent in bad:
            with self.subTest(intent.instrument.market_id or intent.instrument.key), self.assertRaises(RejectedOrder):
                self.broker.submit(intent)
        self.assertEqual(self.broker.open_orders(), [])
        self.assertEqual(self.buy(VERTICAL, "1", "0.55").broker_order_id, "options-shadow-1")  # no number was spent on them

    def test_the_quote_is_every_leg_at_once_at_the_oldest_legs_time(self):
        self.legs.set(occ(581), "1.00", "1.04", at="2026-09-25T13:59:10.000000Z")
        quote = self.broker.quote(structures.instrument(VERTICAL, V))
        self.assertEqual((quote.bid, quote.ask), (D("0.46"), D("0.55")))  # the mark is the bid
        self.assertEqual(quote.as_of, "2026-09-25T13:59:10.000000Z")
        self.quote_condor()
        condor = self.broker.quote(structures.instrument(CONDOR, V))
        self.assertEqual((condor.bid, condor.ask), (D("0.69"), D("0.77")))
        self.legs.rows.pop(occ(586))
        self.later(10)
        with self.assertRaises(VenueUnavailable):
            self.broker.quote(structures.instrument(CONDOR, V))  # a leg with no quote: no structure quote
        with self.assertRaises(VenueUnavailable):
            self.broker.quote(instrument_for(V, {"occ": occ(580)}))

    def test_a_leg_with_no_bid_is_worth_nothing_to_sell_and_one_with_no_ask_cannot_be_bought_back(self):
        self.quote_vertical(low=(None, "0.03"), high=(None, "0.02"))  # both legs far out of the money
        quote = self.broker.quote(structures.instrument(VERTICAL, V))
        self.assertEqual((quote.bid, quote.ask), (D(0), D("0.03")))  # 0 - 0.02 floored; 0.03 - 0
        self.later(10)
        self.quote_vertical(high=("1.00", None))  # the short leg cannot be bought back: no bid for the structure
        quote = self.broker.quote(structures.instrument(VERTICAL, V))
        self.assertEqual((quote.bid, quote.ask), (None, D("0.55")))
        self.buy(VERTICAL, "1", "0.10")
        self.later()
        self.quote_vertical(low=(None, "0.03"), high=(None, "0.02"))  # ask 0.03 <= 0.10, but the legs have no bid
        self.assertEqual(self.broker.advance(), 0)

    def test_a_quote_reads_every_held_and_resting_leg_in_one_request(self):
        self.quote_condor()
        self.buy(CONDOR, "1", "0.77")
        self.legs.calls.clear()
        self.later(10)  # past the quote cache
        self.broker.quote(structures.instrument(VERTICAL, V))
        self.assertEqual(len(self.legs.calls), 1)
        self.assertEqual(set(self.legs.calls[0]), {occ(580), occ(581), occ(575, "P"), occ(576, "P"), occ(585), occ(586)})
        self.broker.quote(structures.instrument(CONDOR, V))  # served from the same read
        self.assertEqual(len(self.legs.calls), 1)


class Opens(ShadowCase):
    def test_an_open_never_fills_in_the_quote_the_decision_saw(self):
        order = self.buy(VERTICAL, "1", "0.55")
        self.assertEqual((order.status, order.filled_quantity), ("accepted", D(0)))
        self.later()
        self.assertEqual(self.broker.advance(), 0)  # the same quote again: nothing
        self.assertEqual(self.held(), {})

    def test_an_open_fills_on_a_newer_quote_at_the_ask_within_its_limit(self):
        order = self.buy(VERTICAL, "1", "0.55")
        self.later()
        self.quote_vertical(high=("1.00", "1.03"), low=("1.50", "1.56"))  # ask 0.56: over the limit
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        self.quote_vertical(low=("1.50", "1.53"))  # ask 1.53 - 1.00 = 0.53: at the ask, not at the limit
        self.assertEqual(self.broker.advance(), 1)
        filled = self.broker.get_order(order.id)
        self.assertEqual((filled.status, filled.filled_quantity, filled.average_price, filled.fees), ("filled", D(1), D("0.53"), D("0.10")))
        self.assertEqual(self.held(), {VERTICAL.code: D(1)})
        self.assertEqual(self.cash_now(), D(10000) - D("53.00") - D("0.10"))
        [fill] = self.broker.fills()
        self.assertEqual((fill.side, fill.quantity, fill.price, fill.fee), ("buy", D(1), D("0.53"), D("0.10")))

    def test_every_leg_must_be_two_sided(self):
        self.buy(VERTICAL, "1", "0.60")
        self.later()
        self.quote_vertical(high=(None, "1.04"))  # the short leg has no bid: the structure cannot be opened
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        self.quote_vertical()
        self.assertEqual(self.broker.advance(), 1)

    def test_a_quote_newer_than_the_accounts_cache_but_not_than_the_order_does_not_fill_it(self):
        self.broker.quote(structures.instrument(VERTICAL, V))  # the account's cache: the quote of 10:00:00
        self.later(2)
        self.quote_vertical()  # re-quoted at 10:00:02, as the House's chain showed it to the deciding agent
        self.buy(VERTICAL, "1", "0.55")  # accepted at 10:00:02, inside the cache's five seconds
        self.later()
        self.assertEqual(self.broker.advance(), 0)  # the quote the decision saw never fills it
        self.later()
        self.quote_vertical()
        self.assertEqual(self.broker.advance(), 1)

    def test_a_leg_quote_that_does_not_change_is_not_newer(self):
        self.buy(VERTICAL, "1", "0.55")
        self.later()
        self.legs.touch(occ(580))  # one leg re-quoted; the other still as the decision saw it
        self.assertEqual(self.broker.advance(), 0)
        self.legs.touch(occ(581))
        self.assertEqual(self.broker.advance(), 1)

    def test_a_credit_structure_opens_at_its_held_price_and_its_cost_is_its_maximum_loss(self):
        self.quote_condor()
        # The least credit to take, 0.23, is a held limit of K - 0.23 = 0.77.
        limit = structures.held_limit(CONDOR, "open", "0.23")
        self.assertEqual(limit, D("0.77"))
        order = self.buy(CONDOR, "2", limit)
        self.later()
        self.quote_condor()
        self.broker.advance()
        order = self.broker.get_order(order.id)
        self.assertEqual((order.status, order.average_price), ("filled", D("0.77")))
        self.assertEqual(self.cash_now(), D(10000) - D("154.00") - D("0.40"))  # two condors: $0.20 each a fill
        [position] = self.broker.positions()
        self.assertEqual((position.quantity, position.average_cost), (D(2), D("0.77")))
        self.assertEqual(position.cost_basis, D(154))  # 2 x $77: the most it can lose

    def test_a_two_expiry_structure_is_quoted_and_opened(self):
        far = occ(580, "C", "261002")
        self.legs.set(occ(580), "2.00", "2.05")
        self.legs.set(far, "2.60", "2.66")
        quote = self.broker.quote(structures.instrument(CALENDAR, V))
        self.assertEqual((quote.bid, quote.ask), (D("0.55"), D("0.66")))  # long far at the ask, short near at the bid
        self.assertEqual(structures.instrument(CALENDAR, V).expiry, "2026-09-28")  # the near leg is its clock
        order = self.buy(CALENDAR, "1", "0.66")
        self.later()
        self.legs.touch(occ(580))
        self.legs.touch(far)
        self.broker.advance()
        self.assertEqual(self.broker.get_order(order.id).average_price, D("0.66"))
        self.assertEqual(self.held(), {CALENDAR.code: D(1)})


class CloseFills(ShadowCase):
    def test_a_close_fills_on_a_newer_quote_at_the_bid_at_or_over_its_limit(self):
        self.own(VERTICAL, 1)
        cash = self.cash_now()
        order = self.sell(VERTICAL, "1", "0.47")
        self.assertEqual(order.status, "accepted")
        self.later()
        self.legs.touch(occ(580))
        self.legs.touch(occ(581))  # bid 0.46: under the limit
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        self.quote_vertical(low=("1.52", "1.56"))  # bid 1.52 - 1.04 = 0.48: at the bid, over the limit
        self.assertEqual(self.broker.advance(), 1)
        order = self.broker.get_order(order.id)
        self.assertEqual((order.status, order.average_price, order.fees), ("filled", D("0.48"), D("0.10")))
        self.assertEqual(self.cash_now(), cash + D("48.00") - D("0.10"))
        self.assertEqual(self.held(), {})

    def test_no_shorts_and_no_leverage(self):
        refused = self.sell(VERTICAL, "1", "0.40")
        self.assertEqual(refused.status, "rejected")
        self.assertIn("no structure to sell", refused.reason)
        small = OptionsShadowBroker(Path(self.dir.name) / "small.json", self.legs, starting_cash="60", clock=self.clock)
        first = small.submit(self.intent(VERTICAL, "buy", "1", "0.55"))
        second = small.submit(self.intent(VERTICAL, "buy", "1", "0.05"))
        self.assertEqual(first.status, "accepted")  # $55.10 held
        self.assertEqual(second.status, "rejected")  # $5.10 more is over the $4.90 left free
        self.assertIn("insufficient cash", second.reason)


class Sizes(ShadowCase):
    def test_ten_percent_of_a_ratio_two_legs_shown_size(self):
        self.legs.set(occ(579), "2.10", "2.15")
        self.legs.set(occ(580), "1.50", "1.55", bid_size="30")  # the body is sold at its bid: 3 contracts, one structure
        self.legs.set(occ(581), "1.00", "1.04")
        order = self.buy(BUTTERFLY, "3", "0.25")  # ask 2.15 + 1.04 - 2 x 1.50 = 0.19
        self.later()
        for symbol in (occ(579), occ(580), occ(581)):
            self.legs.touch(symbol)
        self.assertEqual(self.broker.advance(), 1)
        order = self.broker.get_order(order.id)
        self.assertEqual((order.status, order.filled_quantity, order.average_price), ("partially_filled", D(1), D("0.19")))
        self.assertEqual(order.fees, D("0.20"))  # four contracts a butterfly
        self.later()
        self.assertEqual(self.broker.advance(), 0)  # the same quote gives nothing more
        for symbol in (occ(579), occ(580), occ(581)):
            self.legs.touch(symbol)
        self.broker.advance()
        self.assertEqual(self.broker.get_order(order.id).filled_quantity, D(2))

    def test_partial_fills_rest_and_the_ten_percent_is_shared_by_every_order_on_the_quote(self):
        self.quote_vertical(ask_size="20", bid_size="20")  # 2 structures a quote
        first = self.buy(VERTICAL, "3", "0.55")
        second = self.buy(VERTICAL, "3", "0.55")
        self.later()
        self.quote_vertical(ask_size="20", bid_size="20")
        self.assertEqual(self.broker.advance(), 1)
        self.assertEqual([self.broker.get_order(o.id).filled_quantity for o in (first, second)], [D(2), D(0)])
        self.assertEqual(self.broker.advance(), 0)  # the unchanged quote is spent, for the second order too
        self.later()
        self.quote_vertical(ask_size="20", bid_size="20")
        self.broker.advance()
        self.assertEqual([self.broker.get_order(o.id).filled_quantity for o in (first, second)], [D(3), D(1)])
        self.assertEqual(self.broker.get_order(first.id).status, "filled")
        self.assertEqual(self.broker.get_order(second.id).status, "partially_filled")
        self.assertEqual(self.held(), {VERTICAL.code: D(4)})

    def test_a_restart_does_not_give_the_same_quotes_ten_percent_twice(self):
        self.quote_vertical(ask_size="20", bid_size="20")
        first = self.buy(VERTICAL, "2", "0.55")
        second = self.buy(VERTICAL, "2", "0.55")
        self.later()
        self.quote_vertical(ask_size="20", bid_size="20")
        self.broker.advance()
        self.assertEqual([self.broker.get_order(o.id).filled_quantity for o in (first, second)], [D(2), D(0)])
        again = self.new_broker()
        self.assertEqual(again.advance(), 0)  # the same quote, after a restart: its 10% is spent
        self.assertEqual(again.get_order(second.id).filled_quantity, D(0))

    def test_a_leg_that_shows_no_size_gives_no_fill(self):
        self.buy(VERTICAL, "1", "0.55")
        self.later()
        self.quote_vertical(ask_size=None)
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        self.quote_vertical(ask_size="9")  # 10% of 9 contracts is none
        self.assertEqual(self.broker.advance(), 0)


class Session(ShadowCase):
    def test_orders_only_in_the_regular_session(self):
        self.clock.now = epoch("2026-09-25T12:00:00Z")  # 08:00 New York
        with self.assertRaisesRegex(RejectedOrder, "closed"):
            self.buy(VERTICAL, "1", "0.55")
        self.clock.now = epoch("2026-09-26T15:00:00Z")  # a Saturday
        with self.assertRaisesRegex(RejectedOrder, "closed"):
            self.buy(VERTICAL, "1", "0.55")

    def test_a_day_order_expires_at_the_close_and_nothing_fills_after_it(self):
        self.clock.now = epoch("2026-09-25T19:59:00Z")
        order = self.buy(VERTICAL, "2", "0.55")
        self.clock.now = epoch("2026-09-25T20:00:30Z")
        self.quote_vertical()  # a newer quote, after the bell
        self.assertEqual(self.broker.advance(), 1)
        order = self.broker.get_order(order.id)
        self.assertEqual((order.status, order.filled_quantity), ("expired", D(0)))
        self.assertIn("close", order.reason)
        self.assertEqual(self.held(), {})

    def test_a_structure_whose_first_leg_has_expired_is_refused(self):
        self.clock.now = epoch("2026-09-29T14:00:00Z")
        with self.assertRaisesRegex(RejectedOrder, "expired"):
            self.buy(VERTICAL, "1", "0.55")


class Bookkeeping(ShadowCase):
    def test_the_same_intent_twice_is_one_order_and_cancel_ends_it(self):
        intent = self.intent(VERTICAL, "buy", "1", "0.55")
        first, again = self.broker.submit(intent), self.broker.submit(intent)
        self.assertEqual((first.id, first.broker_order_id), (again.id, again.broker_order_id))
        self.assertEqual(len(self.broker.open_orders()), 1)
        self.assertEqual(self.broker.cancel(first.broker_order_id).status, "cancelled")
        self.assertEqual(self.broker.open_orders(), [])
        with self.assertRaises(RejectedOrder):
            self.broker.get_order("nope")

    def test_a_source_that_cannot_answer_changes_nothing(self):
        self.buy(VERTICAL, "1", "0.55")
        self.later()
        self.quote_vertical()
        self.legs.down = True
        self.assertEqual(self.broker.advance(), 0)
        self.legs.down = False
        self.assertEqual(self.broker.advance(), 1)

    def test_one_read_an_advance_for_every_resting_leg(self):
        self.quote_condor()
        self.buy(VERTICAL, "1", "0.50")
        self.buy(CONDOR, "1", "0.70")
        self.legs.calls.clear()
        self.later()
        self.broker.advance()
        self.assertEqual(len(self.legs.calls), 1)

    def test_a_restart_keeps_cash_positions_and_resting_orders(self):
        self.own(VERTICAL, 1)
        resting = self.sell(VERTICAL, "1", "0.47")
        cash = self.cash_now()
        again = self.new_broker(starting_cash="1")
        self.assertEqual(again.balance().cash, cash)
        self.assertEqual({p.instrument.market_id: p.quantity for p in again.positions()}, {VERTICAL.code: D(1)})
        self.assertEqual([o.id for o in again.open_orders()], [resting.id])
        self.assertEqual(again.submit(self.intent(VERTICAL, "buy", "1", "0.40")).broker_order_id, "options-shadow-3")
        self.later()
        self.quote_vertical(low=("1.52", "1.56"))
        again.advance()
        self.assertEqual(again.get_order(resting.id).status, "filled")
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        state = json.loads(self.path.read_text())
        self.assertIsInstance(state["cash"], str)

    def test_a_write_that_fails_takes_the_order_and_the_fill_back(self):
        resting = self.buy(VERTICAL, "1", "0.55")
        self.later()
        self.quote_vertical()
        with mock.patch("league.options_shadow.os.replace", side_effect=OSError("No space left on device")):
            with self.assertRaises(VenueUnavailable):
                self.buy(VERTICAL, "1", "0.50")
            with self.assertRaises(VenueUnavailable):
                self.broker.advance()
        self.assertEqual((self.cash_now(), self.held()), (D(10000), {}))
        self.assertEqual(self.broker.get_order(resting.id).status, "accepted")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])
        self.assertEqual(self.broker.advance(), 1)  # the disk is back: the fill is made, once, on the same quote
        self.assertEqual(self.buy(VERTICAL, "1", "0.40").broker_order_id, "options-shadow-2")
        self.assertEqual(self.new_broker().balance().cash, self.cash_now())

    def test_resting_buys_hold_their_cash(self):
        self.buy(VERTICAL, "2", "0.55")
        balance = self.broker.balance()
        self.assertEqual((balance.cash, balance.buying_power), (D(10000), D(10000) - D("110.20")))

    def test_a_state_file_that_cannot_be_read_is_an_error_not_a_new_account(self):
        self.path.write_text("{not json")
        with self.assertRaises(BrokerError):
            self.new_broker()


class FeeRule(ShadowCase):
    def test_the_books_fee_model_charges_what_the_account_charges_to_the_cent(self):
        model = Fees("alpaca", option_clearing=True)  # what the House gives a practice Alpaca-family book
        for spec_, contracts in ((VERTICAL, 2), (CONDOR, 4), (BUTTERFLY, 4), (CALENDAR, 2)):
            held = structures.instrument(spec_, V)
            for quantity in (1, 3):
                with self.subTest(spec_.type, quantity=quantity):
                    self.assertEqual(model.charge(held, "buy", D(quantity), D("0.50")).usd, D("0.05") * contracts * quantity)
                    self.assertEqual(model.charge(held, "sell", D(quantity), D("0.50")).usd, D("0.05") * contracts * quantity)
        # The rule is this venue's: a structure on the Alpaca practice account is that account's business.
        self.assertEqual(model.charge(structures.instrument(CONDOR, "alpaca-paper"), "buy", D(1), D("0.50")).usd, D("0.03"))


class Expiry(ShadowCase):
    def test_a_structure_held_past_its_expiry_is_settled_at_its_value_on_the_close(self):
        self.own(VERTICAL, 2)
        resting = self.sell(VERTICAL, "2", "0.90")
        cash = self.cash_now()
        self.closes.prices[("SPY", "2026-09-28")] = D("580.60")
        self.clock.now = epoch("2026-09-28T20:30:00Z")  # after the expiry's bell, still its New York day
        self.assertEqual(self.broker.structure_settlements(), {})
        self.clock.now = epoch("2026-09-29T04:30:00Z")  # 00:30 New York the next day
        self.assertEqual(self.broker.structure_settlements([VERTICAL.code]), {VERTICAL.code: D("0.60")})
        self.assertEqual(self.cash_now(), cash + D("120.00"))  # 0.60 x 100 x 2, no fee
        self.assertEqual(self.held(), {})
        self.assertEqual(self.broker.get_order(resting.id).status, "expired")
        # Read again, it is the same settlement: nothing is paid twice.
        self.assertEqual(self.broker.structure_settlements(), {VERTICAL.code: D("0.60")})
        self.assertEqual(self.cash_now(), cash + D("120.00"))
        self.assertEqual(self.new_broker().structure_settlements(), {VERTICAL.code: D("0.60")})

    def test_no_close_no_settlement(self):
        self.own(VERTICAL, 1)
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.assertEqual(self.broker.structure_settlements(), {})
        self.assertEqual(self.held(), {VERTICAL.code: D(1)})
        self.assertEqual(self.closes.calls, [("SPY", "2026-09-28")])
        self.broker.structure_settlements()
        self.assertEqual(len(self.closes.calls), 1)  # a failed read is not retried every tick

    def test_a_calendar_settles_at_its_far_legs_bid_less_its_near_legs_intrinsic(self):
        far = occ(580, "C", "261002")
        self.legs.set(occ(580), "2.00", "2.05")
        self.legs.set(far, "2.60", "2.66")
        self.buy(CALENDAR, "1", "0.66")
        self.later()
        self.legs.touch(occ(580))
        self.legs.touch(far)
        self.broker.advance()
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.closes.prices[("SPY", "2026-09-28")] = D("581.00")
        self.legs.set(far, "1.80", "1.90")
        self.assertEqual(self.broker.structure_settlements(), {CALENDAR.code: D("0.80")})  # 1.80 - (581 - 580)

    def test_a_calendar_whose_far_leg_cannot_be_read_waits_and_is_never_valued_at_zero_for_it(self):
        far = occ(580, "C", "261002")
        self.legs.set(occ(580), "2.00", "2.05")
        self.legs.set(far, "2.60", "2.66")
        self.buy(CALENDAR, "1", "0.66")
        self.later()
        self.legs.touch(occ(580))
        self.legs.touch(far)
        self.broker.advance()
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.closes.prices[("SPY", "2026-09-28")] = D("581.00")
        self.legs.down = True
        self.assertEqual(self.broker.structure_settlements(), {})  # the source is down: wait
        self.legs.down = False
        self.legs.rows.pop(far)
        self.assertEqual(self.broker.structure_settlements(), {})  # no quote for the far leg: wait
        self.assertEqual(self.held(), {CALENDAR.code: D(1)})
        self.legs.set(far, None, "0.10")  # quoted with no bid: worth nothing to sell, and 1.00 owed on the near leg
        self.assertEqual(self.broker.structure_settlements(), {CALENDAR.code: D(0)})

    def test_the_production_readers(self):
        class Client:
            def __init__(self):
                self.urls = []

            def request(self, method, url, headers=None, what=""):
                self.urls.append(url)
                symbols = url.split("symbols=")[1].split("&")[0].split(",")
                return 200, {"quotes": {s: {"bp": 1.2, "ap": 1.25, "bs": 7, "as": 12, "t": "2026-09-25T14:31:02.123456789Z"}
                                        for s in symbols}}

        client = Client()
        read = alpaca_leg_quotes(client, feed="opra")
        symbols = [occ(500 + i) for i in range(150)]
        rows = read(symbols)
        self.assertEqual(len(client.urls), 2)  # a hundred symbols a request
        self.assertIn("feed=opra", client.urls[0])
        self.assertEqual(rows[symbols[0]], {"bid": D("1.2"), "ask": D("1.25"), "bid_size": D(7), "ask_size": D(12),
                                            "as_of": "2026-09-25T14:31:02.123456Z"})

        class Data:
            def __init__(self):
                self.asked = []

            def bars(self, symbols, timeframe, *, start=None, end=None, limit=120):
                self.asked.append((tuple(symbols), timeframe, start, end))
                return {"SPY": [{"t": "2026-09-28T19:59:00Z", "c": 580.1}, {"t": "2026-09-28T20:00:00Z", "c": 580.55}]}

        data = Data()
        close = alpaca_underlying_close(data)
        self.assertEqual(close("SPY", "2026-09-28"), D("580.55"))
        self.assertEqual(data.asked, [(("SPY",), "1Min", "2026-09-28T19:30:00Z", "2026-09-28T20:00:00Z")])
        self.assertIsNone(close("SPY", "2026-09-27"))  # a Sunday has no session


class BookShadowCase(ShadowCase):
    """`Book` over the shadow account: its helpers, no tests of its own (so a subclass runs only its own)."""

    cash = "100000"

    def setUp(self):
        super().setUp()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.book = self.new_book(self.broker)
        self.book.stake("alice", "200")
        self.vertical = structures.instrument(VERTICAL, V)

    def new_book(self, broker):
        book = Book(V, broker, self.ledger, fees=Fees("alpaca", option_clearing=True), real_money=False, clock=self.clock,
                    market_open=market_hours)
        book.limits["alice"] = Limits(D(100), D(75), asset_classes=("option",))
        return book

    def wish(self, side, quantity, limit):
        self.n += 1
        return Intent.new(agent="alice", instrument=self.vertical, side=side, quantity=quantity, order_type="limit", limit_price=limit,
                          reason=f"test {self.n}", created_at=now_iso(self.clock), nonce=str(self.n))

    def requote(self, **kw):
        self.later()
        self.quote_vertical(**kw)
        self.broker.advance()
        self.book.poll()

    def reconciled(self, book=None):
        result = (book or self.book).reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))
        self.assertIsNone((book or self.book).frozen)

    def fills(self):
        return [row.payload for row in self.ledger.iter(kinds=("book.fill",)) if row.agent == "alice"]


class ThroughTheBook(BookShadowCase):
    """A structure bought, marked, sold flat and settled through `Book`, the one path every venue has."""

    def test_bought_marked_sold_flat_one_closed_trade(self):
        self.reconciled()
        [outcome] = self.book.submit([self.wish("buy", "1", "0.55")])
        self.assertEqual(outcome.status, "resting", outcome.detail)
        self.reconciled()
        self.requote(low=("1.50", "1.53"))  # ask 0.53
        alice = self.book.account("alice")
        self.assertEqual(alice.cash, D(200) - D("53.00") - D("0.10"))
        self.assertEqual(alice.holdings[self.vertical.key].quantity, D(1))
        self.reconciled()
        self.book.mark()
        self.assertEqual(self.book.marks[self.vertical.key], D("0.46"))  # the structure's bid
        self.assertEqual(self.book.equity("alice"), D(200) - D("53.10") + D("46.00"))

        [outcome] = self.book.submit([self.wish("sell", "1", "0.47")])
        self.assertEqual(outcome.status, "resting", outcome.detail)
        self.reconciled()
        self.requote(low=("1.52", "1.56"))  # bid 0.48
        self.reconciled()
        sells = [p for p in self.fills() if p["side"] == "sell"]
        self.assertEqual(len(sells), 1)  # ONE closed trade
        [sale] = sells
        self.assertTrue(sale["flat"])
        # (S sold - S paid) x 100 x 1 - both fills' fees
        self.assertEqual(D(sale["realized"]), (D("0.48") - D("0.53")) * 100 - D("0.20"))
        self.assertEqual(alice.holdings, {})
        self.assertEqual(alice.realized, D("-5.20"))
        self.assertEqual(self.broker.balance().cash, D(100000) - D("5.20"))

        # A House restart: a new account object on the same file, a new book on the same ledger.
        again = self.new_broker(starting_cash="1")
        book = self.new_book(again)
        self.reconciled(book)
        self.assertEqual(book.account("alice").realized, D("-5.20"))

    def test_a_restart_with_a_resting_order_and_a_holding_reconciles(self):
        self.book.submit([self.wish("buy", "1", "0.55")])
        self.requote()
        self.book.submit([self.wish("sell", "1", "0.50")])  # within 10% of the bid 0.46 (the risk engine's limit sanity)
        again = self.new_broker(starting_cash="1")
        book = self.new_book(again)
        self.reconciled(book)
        self.assertEqual(len(book.open_orders("alice")), 1)
        self.later()
        self.quote_vertical(low=("1.56", "1.60"))  # bid 0.52
        again.advance()
        book.poll()
        self.reconciled(book)
        self.assertEqual(book.account("alice").holdings, {})
        self.assertEqual(book.account("alice").realized, (D("0.52") - D("0.55")) * 100 - D("0.20"))

    def entry(self, instrument, limit="0.55"):
        self.n += 1
        return Intent.new(agent="alice", instrument=instrument, side="buy", quantity="1", order_type="limit", limit_price=limit,
                          reason=f"test {self.n}", created_at=now_iso(self.clock), nonce=str(self.n))

    def test_a_structure_is_opened_on_its_expiry_day_until_14_30_new_york_and_a_single_option_is_not(self):
        self.clock.now = epoch("2026-09-28T14:00:00Z")  # 10:00 New York on the vertical's expiry day
        self.quote_vertical()
        [single] = self.book.submit([self.entry(instrument_for(V, {"occ": occ(580)}), "1.55")])
        self.assertEqual(single.status, "refused")
        self.assertIn("an option entry must expire after today", single.detail)  # a single contract: as before
        self.clock.now = epoch("2026-09-28T18:29:00Z")  # 14:29
        self.quote_vertical()
        [early] = self.book.submit([self.entry(self.vertical)])
        self.assertEqual(early.status, "resting", early.detail)
        self.clock.now = epoch("2026-09-28T18:30:00Z")  # 14:30
        self.quote_vertical()
        [late] = self.book.submit([self.entry(self.vertical, "0.54")])
        self.assertEqual(late.status, "refused")
        self.assertIn("a structure is not opened after 14:30 New York on its expiry day", late.detail)
        self.clock.now = epoch("2026-09-29T14:00:00Z")
        self.quote_vertical()
        [gone] = self.book.submit([self.entry(self.vertical, "0.53")])
        self.assertIn("this structure's earliest leg has expired", gone.detail)

    def test_on_an_early_close_the_last_entry_is_ninety_minutes_before_it(self):
        friday = structures.instrument(spec("debit_vertical", (580, "long", "C", "261127", 1), (581, "short", "C", "261127", 1)), V)
        for at, limit in (("2026-11-27T16:29:00Z", "0.55"), ("2026-11-27T16:30:00Z", "0.54")):  # 11:29 and 11:30 New York
            self.clock.now = epoch(at)
            self.legs.set(occ(580, expiry="261127"), "1.50", "1.55")
            self.legs.set(occ(581, expiry="261127"), "1.00", "1.04")
            [outcome] = self.book.submit([self.entry(friday, limit)])
            if limit == "0.55":
                self.assertEqual(outcome.status, "resting", outcome.detail)  # the day after Thanksgiving closes at 13:00
            else:
                self.assertEqual(outcome.status, "refused")
                self.assertIn("a structure is not opened after 11:30 New York on its expiry day "
                              "(ninety minutes before today's early close)", outcome.detail)

    def test_a_structure_whose_bid_comes_to_nothing_is_marked_at_nothing(self):
        self.book.submit([self.wish("buy", "1", "0.55")])
        self.requote()
        self.book.mark()
        self.assertEqual(self.book.marks[self.vertical.key], D("0.46"))
        self.later(10)
        self.legs.rows.pop(occ(581))  # a leg unquoted: no quote at all, and the last mark stands
        self.book.mark()
        self.assertEqual(self.book.marks[self.vertical.key], D("0.46"))
        self.later(10)
        self.quote_vertical(low=("1.00", "1.10"), high=("1.02", "1.06"))  # every leg two-sided; the bid 1.00 - 1.06 is nothing
        self.book.mark()
        self.assertEqual(self.book.marks[self.vertical.key], D(0))
        self.assertEqual(self.book.equity("alice"), D(200) - D("55.10"))
        self.reconciled()

    def test_a_structure_is_never_crossed_inside_the_house(self):
        """Both orders go to the account and each fills against the market alone (review of Sept 25, 2026: the
        House's D3 cross filled the bidder under the ask and the seller in the quote its decision saw)."""
        self.book.stake("bob", "200")
        self.book.limits["bob"] = Limits(D(100), D(75), asset_classes=("option",))
        self.book.submit([self.wish("buy", "1", "0.55")])
        self.requote()
        self.n += 1
        [bid] = self.book.submit([Intent.new(agent="bob", instrument=self.vertical, side="buy", quantity="1", order_type="limit",
                                             limit_price="0.50", reason="bob", created_at=now_iso(self.clock), nonce=str(self.n))])
        self.assertEqual(bid.status, "resting", bid.detail)
        [sale] = self.book.submit([self.wish("sell", "1", "0.46")])  # at or under bob's 0.50: it would have crossed
        self.assertEqual(sale.status, "resting", sale.detail)
        self.assertEqual(len(self.book.open_orders()), 2)
        self.assertEqual([p for p in self.fills() if p["side"] == "sell"], [])
        self.assertFalse([row for row in self.ledger.iter(kinds=("book.cross_plan",))])
        self.requote(low=("1.51", "1.57"))  # bid 0.47, ask 0.57: the sale fills at the bid; bob's bid does not
        self.assertEqual(self.book.account("alice").holdings, {})
        self.assertEqual(self.book.account("bob").holdings, {})
        self.assertEqual(len(self.book.open_orders("bob")), 1)
        self.reconciled()

    def test_a_structure_on_a_book_without_the_settlement_hook_expires_as_before(self):
        from league.tests.fakes import FakeBroker

        fake = FakeBroker("alpaca-paper")
        fake.clock_iso = now_iso(self.clock)
        paper = Book("alpaca-paper", fake, self.ledger, fees=Fees("alpaca"), real_money=False, clock=self.clock)
        paper.limits["alice"] = Limits(D(100), D(75), asset_classes=("option",))
        paper.stake("alice", "200")
        held = structures.instrument(VERTICAL, "alpaca-paper")
        fake.set_quote(held, "0.46", "0.55")
        [outcome] = paper.submit([Intent.new(agent="alice", instrument=held, side="buy", quantity="1", order_type="limit",
                                             limit_price="0.55", reason="x", created_at=now_iso(self.clock), nonce="x")])
        self.assertEqual(outcome.status, "filled", outcome.detail)
        fake.held.clear()  # the venue no longer shows it
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.assertEqual(paper.expire_options(), 1)
        self.assertEqual(paper.account("alice").holdings, {})

    def test_a_partial_fill_is_booked_as_it_comes_and_reconciles_each_time(self):
        cheap = {"low": ("1.20", "1.30"), "ask_size": "10", "bid_size": "10"}  # ask 1.30 - 1.00 = 0.30; one structure a quote
        self.quote_vertical(**cheap)
        [outcome] = self.book.submit([self.wish("buy", "2", "0.30")])
        self.assertEqual(outcome.status, "resting", outcome.detail)
        self.requote(**cheap)
        alice = self.book.account("alice")
        self.assertEqual(alice.holdings[self.vertical.key].quantity, D(1))
        self.assertEqual(len(self.book.open_orders("alice")), 1)  # the rest rests
        self.reconciled()
        self.requote(**{**cheap, "low": ("1.19", "1.29")})  # the second at 0.29
        self.assertEqual(alice.holdings[self.vertical.key].quantity, D(2))
        self.assertEqual(alice.holdings[self.vertical.key].cost, D("30.10") + D("29.10"))
        self.assertEqual(self.book.open_orders("alice"), [])
        self.reconciled()

    def test_two_agents_holding_one_structure_are_each_settled_at_expiry(self):
        self.book.stake("bob", "200")
        self.book.limits["bob"] = Limits(D(100), D(75), asset_classes=("option",))
        self.book.submit([self.wish("buy", "1", "0.55")])
        self.n += 1
        self.book.submit([Intent.new(agent="bob", instrument=self.vertical, side="buy", quantity="1", order_type="limit",
                                     limit_price="0.55", reason="bob", created_at=now_iso(self.clock), nonce=str(self.n))])
        self.requote()
        self.assertEqual(self.broker.positions()[0].quantity, D(2))
        self.reconciled()
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.closes.prices[("SPY", "2026-09-28")] = D("579.00")  # out of the money: worth nothing
        self.assertEqual(self.book.expire_options(), 2)
        for agent in ("alice", "bob"):
            self.assertEqual((self.book.account(agent).holdings, self.book.account(agent).realized), ({}, D("-55.10")))
        self.reconciled()

    def test_a_condors_ledger_ids_fit_the_ledger_whatever_the_agents_name(self):
        """A ledger id is at most 200 characters (`Ledger.append`); a condor's instrument key names all four legs
        (141 characters here). Every row this path writes for one -- intent, order, fill, sale, mark, settlement
        at expiry -- is accepted with a long agent name, and the settlement's id is the same on a second pass."""
        for agent in ("krasker-h4cb387-12", "krasker-h4cb387-12-" + "x" * 40):
            self.book.stake(agent, "200")
            self.book.limits[agent] = Limits(D(100), D(75), asset_classes=("option",))
        self.legs.set(occ(575, "P"), "0.10", "0.12")
        self.legs.set(occ(576, "P"), "0.30", "0.32")
        self.legs.set(occ(585), "0.30", "0.32")
        self.legs.set(occ(586), "0.10", "0.12")  # ask 1 + .12 + .12 - .30 - .30 = 0.64, bid 0.56
        condor = structures.instrument(CONDOR, V)
        self.assertEqual(len(condor.key), 141)
        for agent in ("krasker-h4cb387-12", "krasker-h4cb387-12-" + "x" * 40):
            self.n += 1
            [outcome] = self.book.submit([Intent.new(agent=agent, instrument=condor, side="buy", quantity="1", order_type="limit",
                                                     limit_price="0.64", reason="a condor", created_at=now_iso(self.clock), nonce=str(self.n))])
            self.assertEqual(outcome.status, "resting", outcome.detail)
        self.later()
        for symbol in (occ(575, "P"), occ(576, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.broker.advance()
        self.book.poll()
        self.book.mark()
        self.reconciled()
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.closes.prices[("SPY", "2026-09-28")] = D("580.00")  # between the short strikes: the whole credit kept
        self.assertEqual(self.book.expire_options(), 2)
        self.assertEqual(self.book.expire_options(), 0)
        settles = [row for row in self.ledger.iter(kinds=("book.settle",))]
        self.assertEqual(len(settles), 2)
        for row in settles:
            self.assertEqual(D(row.payload["payout"]), D(100))
            self.assertEqual(D(row.payload["pnl"]), D(100) - D("64.20"))
        ids = [row.id for row in self.ledger.iter()]
        self.assertTrue(ids and all(len(i) <= 200 for i in ids), max(ids, key=len))
        self.reconciled()

    def test_the_expiry_safety_net_books_what_the_account_was_paid(self):
        self.book.submit([self.wish("buy", "1", "0.55")])
        self.requote()
        paid = self.book.account("alice").holdings[self.vertical.key].cost
        self.assertEqual(paid, D("55.10"))
        self.clock.now = epoch("2026-09-29T04:30:00Z")
        self.assertEqual(self.book.expire_options(), 0)  # no close read yet: never written off at zero
        self.assertIn(self.vertical.key, self.book.account("alice").holdings)
        self.reconciled()
        self.clock.advance(600)  # past the close reader's retry wait
        self.closes.prices[("SPY", "2026-09-28")] = D("580.60")
        self.assertEqual(self.book.expire_options(), 1)
        alice = self.book.account("alice")
        self.assertEqual(alice.holdings, {})
        self.assertEqual(alice.realized, D("60.00") - D("55.10"))
        [settle] = [row.payload for row in self.ledger.iter(kinds=("book.settle",))]
        self.assertEqual((D(settle["payout"]), D(settle["pnl"])), (D("60.00"), D("4.90")))
        self.reconciled()
        self.assertEqual(self.book.expire_options(), 0)


class ReviewNoBidWing(BookShadowCase):
    """The review of Sept 25, 2026 (origin/r/shadow 3e6ab4e, `test_review_shadow.NoBidWing`, kept here): a long wing
    quoted with no bid made a held credit structure unsellable, so it was held into its expiry."""

    def test_a_condor_whose_long_wing_has_no_bid_can_still_be_closed_at_its_conservative_bid(self):
        self.book.limits["alice"] = Limits(D(100), D(75), asset_classes=("option",))
        self.legs.set(occ(575, "P"), "0.10", "0.12")
        self.legs.set(occ(576, "P"), "0.30", "0.32")
        self.legs.set(occ(585), "0.30", "0.32")
        self.legs.set(occ(586), "0.10", "0.12")  # ask 1 + .12 + .12 - .30 - .30 = 0.64
        condor = structures.instrument(CONDOR, V)
        [opened] = self.book.submit([Intent.new(agent="alice", instrument=condor, side="buy", quantity="1", order_type="limit",
                                                limit_price="0.64", reason="open", created_at=now_iso(self.clock), nonce="o")])
        self.assertEqual(opened.status, "resting", opened.detail)
        self.later()
        for symbol in (occ(575, "P"), occ(576, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.broker.advance()
        self.book.poll()
        self.assertIn(condor.key, self.book.account("alice").holdings)
        # Late in the day SPY sits between the shorts; the far put wing has no bid (Alpaca: bp 0, bs 0).
        self.later()
        self.legs.set(occ(575, "P"), "0", "0.01", bid_size="0")
        self.legs.set(occ(576, "P"), "0.02", "0.03")
        self.legs.set(occ(585), "0.05", "0.06")
        self.legs.set(occ(586), "0.01", "0.02")
        quote = self.broker.quote(condor)
        self.assertEqual(quote.bid, D("0.92"))  # the mark: K + 0 + .01 - .03 - .06 (the wing worth nothing)
        # The House's close (`_structure_expiry_close`): a sale at the bid, re-sent each tick.
        [sale] = self.book.submit([Intent.new(agent="alice", instrument=condor, side="sell", quantity="1", order_type="limit",
                                              limit_price=quote.bid, reason="close", created_at=now_iso(self.clock), nonce="c")])
        self.assertEqual(sale.status, "resting", sale.detail)
        for _ in range(5):
            self.later()
            for symbol in (occ(575, "P"), occ(576, "P"), occ(585), occ(586)):
                self.legs.touch(symbol)
            self.broker.advance()
            self.book.poll()
        self.assertNotIn(condor.key, self.book.account("alice").holdings,
                         "the condor was never sold at its conservative bid 0.92: every close waits for a bid on the no-bid wing")
        self.reconciled()

    def test_the_exception_is_a_closes_long_leg_only(self):
        self.book.limits["alice"] = Limits(D(100), D(75), asset_classes=("option",))
        for symbol, bid, ask in ((occ(575, "P"), "0.10", "0.12"), (occ(576, "P"), "0.30", "0.32"), (occ(585), "0.30", "0.32"),
                                 (occ(586), "0.10", "0.12")):
            self.legs.set(symbol, bid, ask)
        condor = structures.instrument(CONDOR, V)
        self.book.submit([Intent.new(agent="alice", instrument=condor, side="buy", quantity="1", order_type="limit",
                                     limit_price="0.64", reason="open", created_at=now_iso(self.clock), nonce="o")])
        self.later()
        self.legs.set(occ(575, "P"), None, "0.12")  # an OPEN whose long wing has no bid: never filled
        for symbol in (occ(576, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        for symbol, bid, ask in ((occ(575, "P"), "0.10", "0.12"), (occ(576, "P"), "0.30", "0.32"), (occ(585), "0.30", "0.32"),
                                 (occ(586), "0.10", "0.12")):
            self.legs.set(symbol, bid, ask)
        self.broker.advance()
        self.book.poll()
        self.later()
        self.book.submit([Intent.new(agent="alice", instrument=condor, side="sell", quantity="1", order_type="limit",
                                     limit_price="0.56", reason="close", created_at=now_iso(self.clock), nonce="c")])
        self.later()
        self.legs.set(occ(576, "P"), "0.30", None)  # a CLOSE whose short leg has no ask: never filled
        for symbol in (occ(575, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.assertEqual(self.broker.advance(), 0)
        self.later()
        self.legs.set(occ(576, "P"), "0.30", "0.32", ask_size="5")  # its ask, but under ten contracts: still never
        for symbol in (occ(575, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.assertEqual(self.broker.advance(), 0)


class ReviewStaleLegAtTheFill(ShadowCase):
    """The review of Sept 25, 2026 (`test_review_shadow.StaleLegAtTheFill`, kept here): the fill read no quote age."""

    def test_no_fill_on_a_leg_quote_older_than_the_books_age_rule(self):
        order = self.buy(VERTICAL, "1", "0.55")
        self.later(1)
        self.legs.touch(occ(580))  # 580 quoted once just after the order, then never again
        self.later(40 * 60)
        self.legs.touch(occ(581))  # 581 quoted now
        self.broker.advance()
        self.assertEqual(self.broker.get_order(order.id).filled_quantity, D(0),
                         "filled on a 2,399-second-old quote of the 580 leg (the book's rule is 1,500 s)")
        self.legs.touch(occ(580))
        self.assertEqual(self.broker.advance(), 1)  # quoted again: it fills
        self.assertEqual(self.broker.max_quote_age_seconds, 1500.0)  # the book's own number, read


class ReviewCapAtTheFill(BookShadowCase):
    """The review of Sept 25, 2026 (`test_review_shadow.CapAtTheFill`, adapted): the caps metered a marketable
    limit at the ask it saw, and the account could fill it at a later ask up to the limit, over the order cap.
    Metered at the limit, such an order is refused, and one within the cap can never fill over it."""

    def test_a_structures_maximum_loss_never_exceeds_the_order_cap(self):
        self.quote_vertical(low=("1.60", "1.70"))  # ask 0.70: $70 at the touch
        [over] = self.book.submit([self.wish("buy", "1", "0.77")])
        self.assertEqual(over.status, "refused")
        self.assertIn("order of $77.00 is over the $75 order cap", over.detail)
        [outcome] = self.book.submit([self.wish("buy", "1", "0.74")])
        self.assertEqual(outcome.status, "resting", outcome.detail)
        self.requote(low=("1.66", "1.74"))  # ask 0.74, the limit
        paid = self.book.account("alice").holdings[self.vertical.key].cost
        self.assertLessEqual(paid, D(75))
        self.reconciled()


class ReviewHoldsAsClaimed(ShadowCase):
    """The review of Sept 25, 2026 (`test_review_shadow.HoldsAsClaimed`, kept here)."""

    def test_fees_agree_for_a_condor_of_four_and_a_ratio_two_butterfly(self):
        fees = Fees("alpaca", option_clearing=True)
        for spec_, quantity, expected in ((CONDOR, "4", "0.80"), (BUTTERFLY, "3", "0.60"), (VERTICAL, "7", "0.70")):
            inst = structures.instrument(spec_, V)
            self.assertEqual(fees.charge(inst, "buy", D(quantity), D("0.50")).usd, D(expected))
            self.assertEqual(self.broker._fee(spec_, D(quantity)), D(expected))
        single = structures.instrument(VERTICAL, V)
        self.assertEqual(Fees("alpaca", option_clearing=True).charge(
            structures.spec_of(single).legs[0].instrument, "buy", D(4), D("0.5")).usd, D("0.10"))  # a single contract: as before

    def test_the_entry_cut_is_the_same_minute_in_the_book_and_the_house(self):
        from league.book import _structure_entry_refusal

        self.assertIsNone(_structure_entry_refusal("2026-09-25", "2026-09-25T18:29:59Z"))
        self.assertIsNotNone(_structure_entry_refusal("2026-09-25", "2026-09-25T18:30:00Z"))
        self.assertIsNone(_structure_entry_refusal("2026-09-28", "2026-09-25T19:59:00Z"))


class Service(unittest.TestCase):
    """`service.build` makes the account and its book beside the Kalshi shadow, on a canary too."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)  # registered first, so it runs after every House is closed

    def build(self, root, *, canary):
        from unittest.mock import patch

        from league import service
        from league.tests.fakes import FakeBroker

        def no_network(*args, **kwargs):
            raise OSError("no network in tests")

        config = {**service.load_config(), "feeds": False, "options_history": False, "jev": {"enabled": False}, "real_money": False}
        with patch.object(service, "load_env"), patch.object(service, "secret", return_value="t" * 40), \
                patch("league.venues.gateway_broker", side_effect=lambda venue, **_: FakeBroker(venue)), \
                patch("urllib.request.urlopen", side_effect=no_network):
            house = service.build(root, config=config, research=False, publish=False, merton=False, local_sandbox=True, canary=canary)
        self.addCleanup(house.close, wait=None)
        return house

    def test_the_service_builds_the_account_and_its_practice_book(self):
        from league import service

        for canary in (True, False):
            root = Path(self.dir.name) / f"house-{canary}"
            house = self.build(root, canary=canary)
            book = house.books[V]
            self.assertIsInstance(book.broker, OptionsShadowBroker)
            self.assertEqual(book.broker.state_path, root / "options-shadow.json")
            self.assertFalse(book.real_money)
            self.assertEqual((book.fees.family, book.fees.option_clearing), ("alpaca", True))
            self.assertEqual(book.baseline_cash, D(service.load_config()["options_structures"]["shadow"]["starting_cash"]))
            self.assertIn("kalshi-shadow", house.books)
            self.assertEqual(list(house.books)[-1], V)  # after every other book: the House walks them in this order
        self.assertIn(service.load_config()["options_structures"]["book"], (V, "alpaca-paper"))
        self.assertIsNone(service.options_shadow_broker(Path("/nonexistent"), {"options_structures": {"shadow": {"enabled": False}}}, None, None))


if __name__ == "__main__":
    unittest.main()

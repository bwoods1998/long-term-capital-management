"""Sliced exits: a sell worth more than the order cap goes to the venue as orders of at most the cap.

Workstream C of the Sept 23, 2026 build. A swing's position may now be larger than one order
(`capital.scaled_limits` no longer holds it to four fifths of the $75 cap), so the book must be
able to close it: in slices, each its own venue order with its own deterministic client order id,
every fill attributed to the one intent, the book reconciling after each slice, and a refused or
half-filled slice leaving the rest to the next pass rather than losing it.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument, Quote, RejectedOrder, UnknownOutcome

from league.book import EXIT_PLAN_TTL_SECONDS, GATEWAY_MARKET_MARKUP, Book, Intent, Limits
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker, iso
from league.tests.test_house import HouseCase
from league.tests.test_paper import ScriptedMarketData
from league.tests.test_sim import Touches

D = Decimal
CAP = D("75")


class SliceBroker(FakeBroker):
    """The fake venue, plus what slicing must survive: a refused order, a market order that fills
    only in part (its remainder cancelled, as an immediate-or-cancel order's is), and an answer
    lost after the venue accepted the order. It also keeps the touch each order was sent against,
    so a test can price every order the way the gateway would."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0
        self.reject_at: set[int] = set()  # submit calls (0-based) the venue refuses
        self.reject_all = False
        self.lose_after_accept_at: set[int] = set()  # submit calls accepted (and filled) whose answer is lost
        self.fractions: list[str] = []  # the fill fraction of each next market order, in turn
        self.sent: list[tuple] = []  # (order intent, bid, ask) of every order that reached the venue

    def submit(self, intent):
        call = self.calls
        self.calls += 1
        bid, ask = self.quotes.get(intent.instrument.key, (None, None))
        self.sent.append((intent, bid, ask))
        if self.reject_all or call in self.reject_at:
            self.submitted.append(intent)
            raise RejectedOrder("the venue refused this order")
        saved = self.fill_fraction
        if self.fractions and intent.order_type == "market":
            self.fill_fraction = D(self.fractions.pop(0))
        try:
            order = super().submit(intent)
        finally:
            self.fill_fraction = saved
        if intent.order_type == "market" and not self.asynchronous and order.status in ("accepted", "partially_filled"):
            order.status = "cancelled"  # what did not fill at once is gone
        if call in self.lose_after_accept_at:
            raise UnknownOutcome("the answer was lost after the venue accepted the order")
        return order


def event(leg="yes", venue="kalshi", ticker="KXBTCD-26SEP2317-T80999"):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


def gateway_usd(family, intent, bid, ask):
    """What the gateway counts one order at (`gateway/lib/caps.mjs`, `router.mjs`): an Alpaca market
    order at the venue's ask plus ten per cent, a limit at its limit; a Kalshi order at its own price
    on the leg it trades (a market order crosses at the leg's touch: the ask to buy, the bid to sell)."""
    if family == "alpaca":
        price = intent.limit_price if intent.limit_price is not None else ask * GATEWAY_MARKET_MARKUP
        return intent.quantity * price * intent.instrument.multiplier
    price = intent.limit_price if intent.limit_price is not None else (ask if intent.side == "buy" else bid)
    return intent.quantity * price


class SliceCase(unittest.TestCase):
    venue = "alpaca-paper"
    family = "alpaca"
    real = False
    cash = "100000"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.broker = SliceBroker(self.venue, cash=self.cash, family=self.family)
        self.killed = False
        self.rules = None
        self.book = self.new_book()
        self.book.reconcile()  # a real book opens frozen until it has read the venue
        self.n = 0
        self.checks = []  # (slice index, reconciliation) after every slice routed

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def new_book(self):
        book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=self.real, clock=self.clock,
                    rules=self.rules, kill_switch=lambda: self.killed)
        route = book._route

        def route_then_reconcile(*args, **kwargs):
            out = route(*args, **kwargs)
            if kwargs.get("slice_of") is not None:
                self.checks.append((kwargs["slice_of"][1], book.reconcile()))
            return out

        book._route = route_then_reconcile
        return book

    def with_cap(self, usd):
        self.rules = {"max_order_usd": usd}
        self.book = self.new_book()
        self.book.reconcile()

    def restart(self):
        self.book = self.new_book()
        self.book.limits["a1"] = Limits(D("1000"), CAP)
        return self.book

    def seat(self, agent="a1", usd="1000"):
        self.book.limits[agent] = Limits(D("1000"), CAP)
        self.book.stake(agent, usd)

    def intent(self, agent, instrument, side, quantity, **kw):
        self.n += 1
        return Intent.new(agent=agent, instrument=instrument, side=side, quantity=quantity,
                          reason=kw.pop("reason", f"test {self.n}"), created_at=iso(self.clock), nonce=str(self.n), **kw)

    def buy(self, instrument, *quantities, agent="a1"):
        for quantity in quantities:
            out = self.book.submit([self.intent(agent, instrument, "buy", quantity)])[0]
            self.assertEqual(out.status, "filled", out.detail)

    def held(self, instrument, agent="a1"):
        holding = self.book.account(agent).holdings.get(instrument.key)
        return holding.quantity if holding else D(0)

    def sells(self):
        return [(i, bid, ask) for i, bid, ask in self.broker.sent if i.side == "sell"]

    def plan_rows(self):
        return [e.payload for e in self.ledger.iter(kinds="book.exit_plan")]

    def assert_sound(self, parent_ids=None, unanswered=()):
        """Every order within the cap on the gateway's pricing (the entries that built the position
        too), every sell labelled an exit and sent once; every slice followed by a reconciling book;
        the agents' records intact."""
        for order, bid, ask in self.broker.sent:
            self.assertLessEqual(gateway_usd(self.family, order, bid, ask), CAP, order)
        sells = self.sells()
        for order, bid, ask in sells:
            self.assertLessEqual(gateway_usd(self.family, order, bid, ask), CAP, order)
            self.assertEqual(order.purpose, "exit")
        ids = [order.id for order, _, _ in sells]
        self.assertEqual(len(ids), len(set(ids)), "a client order id was sent twice")
        for index, result in self.checks:
            if index in unanswered:  # the venue's answer was lost: the book rightly will not reconcile until a poll
                self.assertFalse(result.ok)
                self.assertIn("outcome is unknown", result.detail)
                continue
            self.assertTrue(result.ok, f"slice {index}: {result.detail}")
        self.assertTrue(self.book.reconcile().ok)
        self.assertTrue(self.book.evidence_integrity("a1")["ok"])
        self.assertEqual(self.ledger.verify(), self.ledger.head()[0])
        fills = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="a1") if e.payload.get("side") == "sell"]
        if parent_ids is not None:
            self.assertEqual({f["intent_id"] for f in fills}, set(parent_ids))
        slices = [e.payload for e in self.ledger.iter(kinds="book.order") if e.payload.get("slice")]
        by_order = {}
        for row in slices:
            by_order.setdefault(row["order_id"], set()).add((row["slice"]["plan"], row["slice"]["index"]))
        pairs = [next(iter(v)) for v in by_order.values()]
        self.assertEqual(len(pairs), len(set(pairs)), "two venue orders claimed one slice")
        return fills


class CryptoSlices(SliceCase):
    """Alpaca crypto: fractional quantities, the gateway's ten per cent over the touch, the $10 minimum."""

    instrument = Instrument("crypto", "BTC-USD", "alpaca-paper", market_id="BTC/USD")

    def position_worth(self, usd, entries=("0.0008", "0.0008", "0.0008", "0.0001")):
        """Hold BTC in entries of at most the cap on the gateway's own pricing ($64 at the ask is
        $70.41 there), then move the market so it is worth `usd` at the bid."""
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        self.buy(self.instrument, *entries)
        held = self.held(self.instrument)
        bid = (D(usd) / held).quantize(D("0.01"))
        self.broker.set_quote(self.instrument, str(bid), str(bid + 10))
        return held, bid

    def test_a_200_dollar_exit_is_three_orders_of_at_most_the_cap(self):
        held, bid = self.position_worth("200")
        self.assertGreater(held * bid, CAP * 2)
        sell = self.intent("a1", self.instrument, "sell", held)
        out = self.book.submit([sell])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertEqual(out.filled, held)
        self.assertEqual(len(self.sells()), 3)
        self.assertEqual([index for index, _ in self.checks], [0, 1, 2])
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()), D(0)), held)
        self.assertEqual(self.held(self.instrument), 0)
        fills = self.assert_sound([sell.id])
        self.assertEqual(len(fills), 3)
        self.assertEqual([f["flat"] for f in fills], [False, False, True])  # one trade, closed once
        realized = sum((D(f["realized"]) for f in fills), D(0))
        self.assertEqual(realized.quantize(D("0.0001")), self.book.account("a1").realized.quantize(D("0.0001")))
        self.assertEqual(self.plan_rows()[-1]["closed"], "sold")
        self.assertEqual(self.book.exit_plans, {})

    def test_every_slice_is_its_own_order_with_a_distinct_client_id_attributed_to_the_one_intent(self):
        held, _ = self.position_worth("200")
        sell = self.intent("a1", self.instrument, "sell", held)
        self.book.submit([sell])
        orders = [o for o in self.book.orders.values() if o.side == "sell"]
        self.assertEqual(len(orders), 3)
        self.assertEqual({s.intent_id for o in orders for s in o.shares}, {sell.id})
        self.assertEqual(sorted(o.slice_index for o in orders), [0, 1, 2])
        self.assertEqual(len({o.order_id for o in orders}), 3)
        self.assertTrue(all(o.slice_of == f"exit-plan:{self.venue}:{sell.id}" for o in orders))

    def test_an_exit_under_the_cap_is_one_order_and_no_plan(self):
        held, _ = self.position_worth("60")
        out = self.book.submit([self.intent("a1", self.instrument, "sell", held)])[0]
        self.assertEqual(out.status, "filled")
        self.assertEqual(len(self.sells()), 1)
        self.assertEqual(self.plan_rows(), [])
        self.assertTrue(self.book.reconcile().ok)

    def test_entries_are_unchanged(self):
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        out = self.book.submit([self.intent("a1", self.instrument, "buy", "0.002")])[0]  # $160: one entry over the cap
        self.assertEqual(out.status, "refused")
        self.assertIn("order cap", out.detail)
        self.assertEqual(self.broker.sent, [])

    def test_a_market_entry_is_held_to_the_cap_on_the_gateways_own_pricing(self):
        """Review, Sept 23, 2026: the gateway counts an Alpaca market buy (the adapter sends `qty`) at
        the touch plus ten per cent, so a buy of $74.41 at the ask is $81.85 there and gets a 403.
        The real book refuses it first and says why; the paper account, whose gateway route takes no
        caps, is unchanged. A $60 order, the most `capital.scaled_limits` now gives, passes."""
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        out = self.book.submit([self.intent("a1", self.instrument, "buy", "0.00093")])[0]
        if self.real:
            self.assertEqual(out.status, "refused")
            self.assertIn("counts as $81.85 at the gateway", out.detail)
            self.assertEqual(self.broker.sent, [])
        else:
            self.assertEqual(out.status, "filled", out.detail)
        out = self.book.submit([self.intent("a1", self.instrument, "buy", "0.00075")])[0]  # $60.01 at the ask, $66.01 there
        self.assertEqual(out.status, "filled", out.detail)
        if self.real:
            self.assert_sound()  # every order that reached the venue fits the gateway's cap

    def test_a_limit_entry_counts_at_its_own_limit(self):
        """The gateway counts a limit order at its limit, so a marketable limit above the ask is dearer
        there than on the book's count at the ask; a bid resting under the touch is not."""
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        over = self.book.submit([self.intent("a1", self.instrument, "buy", "0.00093", order_type="limit", limit_price="81000")])[0]
        if self.real:  # $74.41 at the ask, $75.33 at its limit
            self.assertEqual(over.status, "refused")
            self.assertIn("counts as $75.33 at the gateway (its limit price)", over.detail)
            self.assertEqual(self.broker.sent, [])
        else:
            self.assertNotEqual(over.status, "refused", over.detail)
        under = self.book.submit([self.intent("a1", self.instrument, "buy", "0.00093", order_type="limit", limit_price="79990")])[0]
        self.assertNotEqual(under.status, "refused", under.detail)  # $74.39 on both counts
        self.assertLessEqual(gateway_usd(self.family, *self.broker.sent[-1]), CAP)

    def test_a_pool_of_market_entries_is_never_one_order_over_the_cap_at_the_gateway(self):
        """Two agents' $35 buys are $70.40 at the ask but $77.45 on the gateway's pricing: pooled into
        one venue order, both were refused with a 403. Each now goes as its own order."""
        self.seat("a1")
        self.seat("a2")
        self.broker.set_quote(self.instrument, "80000", "80010")
        outs = self.book.submit([self.intent("a1", self.instrument, "buy", "0.00044"), self.intent("a2", self.instrument, "buy", "0.00044")])
        self.assertEqual([o.status for o in outs], ["filled", "filled"], [o.detail for o in outs])
        buys = [(o, bid, ask) for o, bid, ask in self.broker.sent if o.side == "buy"]
        self.assertEqual(len(buys), 2)
        for sent in buys:
            self.assertLessEqual(gateway_usd(self.family, *sent), CAP)
        self.assertTrue(self.book.reconcile().ok)

    def test_a_venue_that_fills_a_moment_later_gets_every_slice_at_once(self):
        """Alpaca's habit: an order is accepted first and filled on a later read. Each working slice
        already holds its own units, so the next one goes at once, and none oversells."""
        held, _ = self.position_worth("200")
        self.broker.asynchronous = True
        sell = self.intent("a1", self.instrument, "sell", held)
        out = self.book.submit([sell])[0]
        self.assertEqual(out.status, "sent", out.detail)
        self.assertEqual(len(self.sells()), 3)
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()), D(0)), held)
        self.assertEqual(self.held(self.instrument), held)  # nothing has filled yet
        self.book.poll()
        self.assertEqual(self.held(self.instrument), 0)
        self.assertEqual(len(self.sells()), 3)
        self.assertEqual(self.book.exit_plans, {})
        self.assert_sound([sell.id])

    def test_a_partly_filled_slice_leaves_the_rest_to_the_next_pass(self):
        held, _ = self.position_worth("200")
        self.broker.fractions = ["0.5"]
        out = self.book.submit([self.intent("a1", self.instrument, "sell", held)])[0]
        self.assertEqual(out.status, "partial", out.detail)
        self.assertIn("the rest follows", out.detail)
        self.assertEqual(len(self.sells()), 1)
        first = self.sells()[0][0].quantity
        self.assertEqual(self.held(self.instrument), held - first / 2)
        self.assertTrue(self.book.reconcile().ok)
        self.book.poll()
        # The next slice sized off what was still held, not off the plan's first cut.
        second = self.sells()[1][0].quantity
        self.assertLess(second, held - first / 2)
        self.assertEqual(self.held(self.instrument), 0)
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()[1:]), D(0)), held - first / 2)
        self.assert_sound()

    def test_a_refused_slice_does_not_lose_the_remainder(self):
        held, _ = self.position_worth("200")
        self.broker.reject_at = {self.broker.calls + 1}  # the second slice
        sell = self.intent("a1", self.instrument, "sell", held)
        out = self.book.submit([sell])[0]
        self.assertEqual(out.status, "partial")
        self.assertEqual(len(self.sells()), 2)
        rejected = [o for o in self.book.orders.values() if o.status == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].slice_index, 1)
        self.assertGreater(self.held(self.instrument), 0)
        self.assertTrue(self.book.reconcile().ok)
        self.book.poll()  # the next pass retries what is left, as a new slice with a new id
        self.assertEqual(self.held(self.instrument), 0)
        self.assertEqual(sorted(o.slice_index for o in self.book.orders.values() if o.side == "sell"), [0, 1, 2, 3])
        self.assert_sound([sell.id])

    def test_the_remainder_never_goes_as_an_order_under_the_venue_minimum(self):
        """$80 is not $75 and a $5 order Alpaca refuses: it is two orders of about $40."""
        held, bid = self.position_worth("80", entries=("0.0005", "0.0005"))
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        sells = self.sells()
        self.assertEqual(len(sells), 2)
        for order, b, _ in sells:
            self.assertGreaterEqual(order.quantity * b, D("10"))
        self.assertEqual(self.held(self.instrument), 0)
        self.assert_sound()

    def test_under_a_small_cap_parts_under_the_minimum_are_merged_not_sent(self):
        self.with_cap("15")
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        self.buy(self.instrument, "0.00015")  # $12
        held = self.held(self.instrument)
        bid = (D("16") / held).quantize(D("0.01"))
        self.broker.set_quote(self.instrument, str(bid), str(bid + 1))
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        sells = self.sells()
        # Two $8 halves would each be refused by the venue: one $16 order goes instead.
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0][0].quantity, held)
        self.assertEqual(self.held(self.instrument), 0)
        self.assertTrue(self.book.reconcile().ok)

    def test_under_a_small_cap_parts_over_the_minimum_are_still_cut(self):
        self.with_cap("15")
        self.seat()
        self.broker.set_quote(self.instrument, "80000", "80010")
        self.buy(self.instrument, "0.00015")
        held = self.held(self.instrument)
        bid = (D("25") / held).quantize(D("0.01"))
        self.broker.set_quote(self.instrument, str(bid), str(bid + 1))
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        sells = self.sells()
        self.assertEqual(len(sells), 2)
        for order, b, a in sells:
            self.assertGreaterEqual(order.quantity * b, D("10"))
            self.assertLessEqual(order.quantity * a * GATEWAY_MARKET_MARKUP, D("15"))
        self.assertEqual(self.held(self.instrument), 0)

    def test_a_restart_after_an_accepted_slice_whose_answer_was_lost_sends_nothing_twice(self):
        held, _ = self.position_worth("200")
        self.broker.lose_after_accept_at = {self.broker.calls + 1}  # the second slice: accepted and filled, answer lost
        sell = self.intent("a1", self.instrument, "sell", held)
        out = self.book.submit([sell])[0]
        self.assertEqual(len(self.sells()), 2)
        self.assertEqual(out.status, "partial")
        # A restart: the ledger knows slice 1 went out and not what became of it.
        book = self.restart()
        book.poll()  # the startup poll books what the venue did; it sends nothing before a reconcile
        self.assertEqual(len(self.sells()), 2)
        self.assertTrue(book.reconcile().ok)
        book.poll()
        self.assertEqual(self.held(self.instrument), 0)
        self.assertEqual(len(self.sells()), 3)
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()), D(0)), held)
        self.assert_sound([sell.id], unanswered={1})

    def test_a_restart_after_a_slice_that_never_arrived_resends_only_the_remainder(self):
        held, _ = self.position_worth("200")
        self.broker.lose_next_submit = False
        original = self.broker.submit
        calls = {"n": 0}

        def lose_second(intent):
            calls["n"] += 1
            if calls["n"] == 2:
                self.broker.lose_next_submit = True  # FakeBroker: the order never reaches its book
            return original(intent)

        self.broker.submit = lose_second
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        self.broker.submit = original
        book = self.restart()
        book.poll()  # the venue has no such order: heard once, the slice stays unknown and the plan waits
        self.assertFalse(book.reconcile().ok)
        self.clock.advance(61)
        book.poll()  # heard again a minute later: the slice is closed as never arrived
        self.assertTrue(book.reconcile().ok)
        book.poll()
        self.assertEqual(self.held(self.instrument), 0)
        statuses = sorted((o.slice_index, o.status) for o in book.orders.values() if o.side == "sell")
        self.assertEqual(statuses[1], (1, "rejected"))  # the venue had no such order
        ids = [o.id for o, _, _ in self.sells()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(book.reconcile().ok)

    def test_a_limit_exit_rests_in_slices_and_fills_slice_by_slice(self):
        held, bid = self.position_worth("200")
        limit = (bid * D("1.01")).quantize(D("0.01"))
        sell = self.intent("a1", self.instrument, "sell", held, order_type="limit", limit_price=str(limit))
        out = self.book.submit([sell])[0]
        self.assertEqual(out.status, "resting", out.detail)
        resting = [o for o in self.book.orders.values() if o.side == "sell" and o.open]
        self.assertEqual(len(resting), 3)
        for order, _, _ in self.sells():
            self.assertLessEqual(order.quantity * limit, CAP)
        self.book.poll()
        self.assertEqual(len(self.sells()), 3)  # all of it is working: nothing more to send
        for working in resting:
            self.broker.fill_resting(working.order_id, str(working.quantity))
            self.book.poll()
            self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.held(self.instrument), 0)
        self.assertEqual(self.book.exit_plans, {})
        self.assert_sound([sell.id])

    def test_cancelling_a_slice_withdraws_the_rest_of_the_exit(self):
        held, bid = self.position_worth("200")
        self.broker.fractions = ["0.5"]
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        limit_exit = [o for o in self.book.orders.values() if o.side == "sell"]
        self.assertEqual(len(limit_exit), 1)
        # A resting limit slice, cancelled by its agent.
        self.book.submit([self.intent("a1", self.instrument, "sell", self.held(self.instrument), order_type="limit",
                                      limit_price=str((bid * D("1.01")).quantize(D("0.01"))))])
        resting = [o for o in self.book.orders.values() if o.side == "sell" and o.open]
        self.assertTrue(resting)
        self.assertEqual(len(self.book.exit_plans), 1)
        self.book.cancel("a1", resting[0].order_id)
        self.assertEqual(self.book.exit_plans, {})
        sent = len(self.sells())
        self.book.poll()
        self.assertEqual(len(self.sells()), sent)
        self.assertTrue(self.book.reconcile().ok)

    def test_a_newer_sell_supersedes_an_unfinished_exit(self):
        held, _ = self.position_worth("200")
        self.broker.fractions = ["0.5"]
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        left = self.held(self.instrument)
        small = (left / 4).quantize(D("0.000000001"))
        out = self.book.submit([self.intent("a1", self.instrument, "sell", small)])[0]
        self.assertEqual(out.status, "filled")
        closed = [p for p in self.plan_rows() if p.get("closed")]
        self.assertEqual(len(closed), 1)
        self.assertIn("superseded", closed[0]["closed"])
        self.book.poll()
        self.assertEqual(self.held(self.instrument), left - small)  # the old plan sold nothing more
        self.assertTrue(self.book.reconcile().ok)

    def test_a_blocked_exit_is_refused_once_on_the_record_and_resumes(self):
        held, _ = self.position_worth("200")
        self.broker.fractions = ["0.5"]
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        self.killed = True
        for _ in range(3):
            self.book.poll()
        refused = [e.payload for e in self.ledger.iter(kinds="book.refused") if e.payload.get("slice_of")]
        self.assertEqual(len(refused), 1)
        self.assertIn("kill switch engaged", refused[0]["reasons"])
        self.assertEqual(len(self.sells()), 1)
        self.killed = False
        self.book.poll()
        self.assertEqual(self.held(self.instrument), 0)
        self.assert_sound()

    def test_a_blocked_exit_ends_after_its_hour(self):
        held, _ = self.position_worth("200")
        self.broker.fractions = ["0.5"]
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        self.killed = True
        self.book.poll()
        self.clock.advance(EXIT_PLAN_TTL_SECONDS + 1)
        self.book.poll()
        self.assertEqual(self.book.exit_plans, {})
        self.assertIn("not finished within 60 minutes", self.plan_rows()[-1]["closed"])
        self.killed = False
        self.book.poll()
        self.assertEqual(len(self.sells()), 1)
        self.assertGreater(self.held(self.instrument), 0)

    def test_an_exit_the_venue_keeps_refusing_stops_at_its_order_budget(self):
        held, _ = self.position_worth("200")
        self.broker.reject_all = True
        self.book.submit([self.intent("a1", self.instrument, "sell", held)])
        plan = next(iter(self.book.exit_plans.values()))
        for _ in range(plan.max_orders + 3):
            self.book.poll()
        self.assertEqual(self.book.exit_plans, {})
        self.assertEqual(len(self.sells()), plan.max_orders)
        self.assertIn("the most one exit may send", self.plan_rows()[-1]["closed"])
        self.assertEqual(self.held(self.instrument), held)
        self.assertTrue(self.book.reconcile().ok)

    def test_an_exit_crossed_in_part_inside_the_house_slices_only_the_residual(self):
        held, bid = self.position_worth("200")
        self.book.limits["b1"] = Limits(D("1000"), CAP)
        self.book.stake("b1", "1000")
        buy = self.intent("b1", self.instrument, "buy", (D("40") / (bid + 10)).quantize(D("0.000000001")))
        sell = self.intent("a1", self.instrument, "sell", held)
        outs = self.book.submit([buy, sell])
        self.assertEqual({o.status for o in outs if o.agent == "b1"}, {"crossed"})
        residual = held - buy.quantity
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()), D(0)), residual)
        self.assertEqual(len(self.sells()), 3)  # about $160 of it went to the venue
        self.assertEqual(self.held(self.instrument), 0)
        self.assertTrue(self.book.reconcile().ok)


class RealCryptoSlices(CryptoSlices):
    venue = "alpaca"
    real = True
    cash = "5000"
    instrument = Instrument("crypto", "BTC-USD", "alpaca", market_id="BTC/USD")


class EquitySlices(SliceCase):
    """Alpaca equities: fractional shares at market, no venue minimum, whole shares at a limit."""

    instrument = Instrument("equity", "SPY", "alpaca-paper")

    def test_a_fractional_equity_exit_is_cut_under_the_cap(self):
        self.seat()
        self.broker.set_quote(self.instrument, "500.00", "500.05")
        self.buy(self.instrument, "0.13", "0.13", "0.13", "0.03")  # $65 at the ask is $71.51 at the gateway
        held = self.held(self.instrument)
        sell = self.intent("a1", self.instrument, "sell", held)
        self.assertEqual(self.book.submit([sell])[0].status, "filled")
        self.assertEqual(len(self.sells()), 4)  # $210 at the bid is $231 on the gateway's pricing
        self.assertEqual(self.held(self.instrument), 0)
        self.assert_sound([sell.id])

    def test_a_small_cap_cuts_equities_without_a_minimum_to_merge_on(self):
        self.with_cap("15")
        self.seat()
        self.broker.set_quote(self.instrument, "100.00", "100.01")
        self.buy(self.instrument, "0.12")
        self.broker.set_quote(self.instrument, "133.33", "133.34")  # $16
        self.book.submit([self.intent("a1", self.instrument, "sell", "0.12")])
        self.assertEqual(len(self.sells()), 2)  # two $8 orders: the $10 minimum is Alpaca crypto's alone
        self.assertEqual(self.held(self.instrument), 0)

    def test_one_whole_share_worth_more_than_the_cap_goes_as_one_unit(self):
        self.seat()
        self.broker.set_quote(self.instrument, "65.00", "65.01")
        self.buy(self.instrument, "1")  # $71.51 on the gateway's pricing
        self.broker.set_quote(self.instrument, "90.00", "90.01")
        sell = self.intent("a1", self.instrument, "sell", "1", order_type="limit", limit_price="89.00")
        self.assertEqual(self.book.submit([sell])[0].status, "filled")
        self.assertEqual([o.quantity for o, _, _ in self.sells()], [D("1")])
        self.assertTrue(self.book.reconcile().ok)


class RealEquitySlices(EquitySlices):
    venue = "alpaca"
    real = True
    cash = "5000"
    instrument = Instrument("equity", "SPY", "alpaca")


class KalshiSlices(SliceCase):
    """Kalshi: whole contracts, YES and NO legs, and the v2 wire the adapter would send."""

    venue = "kalshi-shadow"
    family = "kalshi"
    cash = "5000"

    def contracts(self, leg="yes", count="200"):
        instrument = event(leg, self.venue)
        self.seat()
        self.broker.set_quote(instrument, "0.28", "0.30")
        self.buy(instrument, count)  # $60: one order
        self.broker.set_quote(instrument, "0.94", "0.95")
        return instrument

    def test_a_kalshi_entry_counts_at_its_own_price_not_marked_up(self):
        """Kalshi's v2 wire has no market order: the adapter crosses at the leg's touch, and the
        gateway counts a contract at the price it carries. A $75 market buy passes; a marketable
        limit above the ask counts at its limit, and the real book refuses it before the gateway."""
        instrument = event("yes", self.venue)
        self.seat()
        self.broker.set_quote(instrument, "0.28", "0.30")
        over = self.book.submit([self.intent("a1", instrument, "buy", "250", order_type="limit", limit_price="0.31")])[0]
        if self.real:  # $75.00 at the ask, $77.50 at its limit
            self.assertEqual(over.status, "refused")
            self.assertIn("counts as $77.50 at the gateway (its limit price)", over.detail)
            self.assertEqual(self.broker.sent, [])
        else:
            self.assertNotEqual(over.status, "refused", over.detail)
        out = self.book.submit([self.intent("a1", instrument, "buy", "250")])[0]  # $75.00 at the touch on both counts
        self.assertNotEqual(out.status, "refused", out.detail)
        self.assertLessEqual(gateway_usd(self.family, *self.broker.sent[-1]), CAP)

    def test_a_contract_exit_is_cut_into_whole_contracts_under_the_cap(self):
        instrument = self.contracts()
        sell = self.intent("a1", instrument, "sell", "200")
        out = self.book.submit([sell])[0]
        self.assertEqual(out.status, "filled", out.detail)
        counts = [o.quantity for o, _, _ in self.sells()]
        self.assertEqual(counts, [D(66), D(67), D(67)])
        self.assertTrue(all(c == c.to_integral_value() for c in counts))
        self.assertEqual(self.held(instrument), 0)
        fills = self.assert_sound([sell.id])
        self.assertEqual([f["flat"] for f in fills], [False, False, True])

    def test_a_no_leg_exit_is_cut_on_its_own_leg(self):
        instrument = self.contracts("no")
        sell = self.intent("a1", instrument, "sell", "200")
        self.assertEqual(self.book.submit([sell])[0].status, "filled")
        self.assertEqual(len(self.sells()), 3)
        self.assertTrue(all(o.instrument.right == "no" for o, _, _ in self.sells()))
        self.assertEqual(self.held(instrument), 0)
        self.assert_sound([sell.id])

    def test_every_slice_is_a_v2_order_the_gateway_prices_under_the_cap(self):
        from ltcm.adapters import GatewaySigner, KalshiCredentials, VenueClient
        from ltcm.adapters.kalshi import KalshiBroker

        self.seat()
        for leg in ("yes", "no"):
            with self.subTest(leg=leg):
                self.broker.sent.clear()
                instrument = event(leg, self.venue, ticker=f"KXTEST-26SEP23-{leg.upper()}")
                self.broker.set_quote(instrument, "0.28", "0.30")
                self.buy(instrument, "200")
                self.broker.set_quote(instrument, "0.94", "0.95")
                self.book.submit([self.intent("a1", instrument, "sell", "200")])
                yes_bid, yes_ask = (D("0.94"), D("0.95")) if leg == "yes" else (D("0.05"), D("0.06"))

                class MarketData:
                    def quote(self, inst):
                        return Quote(inst, yes_bid, yes_ask, None, "2026-09-23T07:00:00Z", "fake", delayed=False)

                    def price_ranges(self, ticker):
                        return [{"start": D("0.01"), "end": D("0.99"), "step": D("0.01")}]

                signer = GatewaySigner("t" * 40)
                adapter = KalshiBroker(KalshiCredentials("gateway", signer), market_data=MarketData(), clock=self.clock,
                                       client=VenueClient(None, gateway_url="https://gateway.test", gateway=signer, venue="kalshi"))
                for order, _, _ in self.sells():
                    real = order.__class__.new(**{**{k: getattr(order, k) for k in ("desk_id", "side", "quantity", "order_type", "limit_price",
                                                                                       "time_in_force", "rationale", "created_at", "purpose",
                                                                                       "exit_reason", "exit_of")},
                                                  "instrument": Instrument("event", instrument.symbol, "kalshi", market_id=instrument.market_id, right=leg)})
                    body = adapter.order_body(real)
                    self.assertEqual(body["side"], "ask" if leg == "yes" else "bid")  # a YES sale sells YES; a NO sale buys YES
                    count, price = D(body["count"]), D(body["price"])
                    self.assertEqual(count, count.to_integral_value())
                    # The gateway's exit pricing (`kalshiNotional`, exit=true): the complement on the bid side.
                    leg_price = (1 - price) if body["side"] == "bid" else price
                    self.assertLessEqual(count * leg_price, CAP)
                self.assertEqual(self.held(instrument), 0)

    def test_a_half_filled_contract_slice_is_resized_on_the_next_pass(self):
        instrument = self.contracts()
        self.broker.fractions = ["0.5"]
        out = self.book.submit([self.intent("a1", instrument, "sell", "200")])[0]
        self.assertEqual(out.status, "partial")
        self.assertEqual(self.held(instrument), D(167))  # 66 sent, 33 filled, the rest cancelled
        self.assertTrue(self.book.reconcile().ok)
        self.book.poll()
        counts = [o.quantity for o, _, _ in self.sells()]
        self.assertEqual(counts[0], D(66))
        self.assertEqual(sum(counts[1:], D(0)), D(167))
        self.assertEqual(self.held(instrument), 0)
        self.assert_sound()

    def test_a_restart_mid_exit_resumes_without_sending_a_slice_twice(self):
        instrument = self.contracts()
        self.broker.fractions = ["0.5"]
        sell = self.intent("a1", instrument, "sell", "200")
        self.book.submit([sell])
        before = len(self.sells())
        book = self.restart()
        self.assertEqual(len(book.exit_plans), 1)
        book.poll()  # before this process has read the venue: nothing is sent
        self.assertEqual(len(self.sells()), before)
        self.assertTrue(book.reconcile().ok)
        book.poll()
        self.assertEqual(self.held(instrument), 0)
        self.assertEqual(sorted(o.slice_index for o in book.orders.values() if o.side == "sell"), list(range(len(self.sells()))))
        self.assertEqual(sum((o.quantity for o, _, _ in self.sells()), D(0)) - D(33), D(200))  # 33 of the first slice never filled
        self.assert_sound([sell.id])
        book.poll()
        self.restart().poll()
        self.assertEqual(len(self.sells()), before + 3)  # a closed plan is not resumed by another restart


class RealKalshiSlices(KalshiSlices):
    venue = "kalshi"
    real = True


class PaperVenueSlices(unittest.TestCase):
    """The practice venues themselves, not the fake: the Kalshi shadow account (fills in full at the
    touch, conservatively) and the canary's simulated Alpaca account (accepts first, fills on the
    next read)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def intent(self, instrument, side, quantity, n):
        return Intent.new(agent="a1", instrument=instrument, side=side, quantity=quantity, reason="test",
                          created_at=iso(self.clock), nonce=str(n))

    def test_the_kalshi_shadow_account_takes_an_exit_in_whole_contract_slices(self):
        from league.paper import KalshiShadowBroker

        ticker = "KXBTCD-26SEP2317-T80999"
        data = ScriptedMarketData(self.clock)
        data.set(ticker, "0.28", "0.30")
        venue = KalshiShadowBroker(Path(self.dir.name) / "kalshi-shadow.json", data, starting_cash="5000", clock=self.clock)
        sent = []
        submit = venue.submit
        venue.submit = lambda intent: (sent.append(intent), submit(intent))[1]
        book = Book("kalshi-shadow", venue, self.ledger, fees=Fees("kalshi"), real_money=False, clock=self.clock)
        self.assertTrue(book.reconcile().ok)
        book.limits["a1"] = Limits(D("1000"), CAP)
        book.stake("a1", "1000")
        for n, leg in enumerate(("yes", "no")):
            with self.subTest(leg=leg):
                sent.clear()
                instrument = Instrument("event", ticker, "kalshi-shadow", market_id=ticker, right=leg)
                data.set(ticker, "0.28", "0.30") if leg == "yes" else data.set(ticker, "0.70", "0.72")
                self.assertEqual(book.submit([self.intent(instrument, "buy", "200", 10 + n)])[0].status, "filled")  # $60
                data.set(ticker, "0.94", "0.95") if leg == "yes" else data.set(ticker, "0.05", "0.06")
                out = book.submit([self.intent(instrument, "sell", "200", 20 + n)])[0]
                self.assertEqual(out.status, "filled", out.detail)
                sells = [i for i in sent if i.side == "sell"]
                self.assertEqual([i.quantity for i in sells], [D(66), D(67), D(67)])
                for order in sells:
                    self.assertLessEqual(order.quantity * D("0.94"), CAP)  # the leg's bid, where a market sell crosses
                self.assertNotIn(instrument.key, book.account("a1").holdings)
                self.assertEqual(venue.positions(), [])
                self.assertTrue(book.reconcile().ok)
        self.assertTrue(book.evidence_integrity("a1")["ok"])

    def test_the_canarys_simulated_alpaca_account_fills_every_slice_on_the_next_read(self):
        from league.sim import SimBroker

        btc = Instrument("crypto", "BTC-USD", "alpaca-paper", market_id="BTC/USD")
        touch = Touches()
        touch.set(btc, "80000", "80010")
        venue = SimBroker(Path(self.dir.name) / "sim.json", touch, clock=self.clock)
        sent = []
        submit = venue.submit
        venue.submit = lambda intent: (sent.append(intent), submit(intent))[1]
        book = Book("alpaca-paper", venue, self.ledger, fees=Fees("alpaca"), real_money=False, clock=self.clock)
        self.assertTrue(book.reconcile().ok)
        book.limits["a1"] = Limits(D("1000"), CAP)
        book.stake("a1", "1000")
        for n, quantity in enumerate(("0.0009", "0.0009", "0.0007")):
            book.submit([self.intent(btc, "buy", quantity, n)])
            book.poll()
        held = book.account("a1").holdings[btc.key].quantity
        self.assertTrue(book.reconcile().ok)
        bid = (D("200") / held).quantize(D("0.01"))
        touch.set(btc, str(bid), str(bid + 10))
        out = book.submit([self.intent(btc, "sell", held, 9)])[0]
        self.assertEqual(out.status, "sent", out.detail)  # accepted: the simulated venue fills on its next read
        sells = [i for i in sent if i.side == "sell"]
        self.assertEqual(len(sells), 3)
        for order in sells:
            self.assertLessEqual(order.quantity * (bid + 10) * GATEWAY_MARKET_MARKUP, CAP)
        book.poll()
        self.assertNotIn(btc.key, book.account("a1").holdings)
        self.assertEqual(book.exit_plans, {})
        self.assertTrue(book.reconcile().ok)
        self.assertTrue(book.evidence_integrity("a1")["ok"])


class HouseExitSlices(HouseCase):
    """The House's own paths to an exit: an agent selling at its wake, and a wind-down at death."""

    def hold(self, agent, usd="200"):
        book = self.house.books["alpaca-paper"]
        self.house.seat(agent)
        book.limits[agent.id] = Limits(D("1000"), CAP)  # a swing's position: more than one order can close
        book.stake(agent.id, "300", note="test: room for a swing-sized position")
        for n, quantity in enumerate(("0.0009", "0.0009", "0.0007")):
            out = book.submit([Intent.new(agent=agent.id, instrument=self.btc, side="buy", quantity=quantity, reason="test entry",
                                          created_at=iso(self.clock), nonce=f"hold-{n}")])[0]
            self.assertEqual(out.status, "filled", out.detail)
        held = book.account(agent.id).holdings[self.btc.key].quantity
        bid = (D(usd) / held).quantize(D("0.01"))
        self.broker.set_quote(self.btc, str(bid), str(bid + 10))
        return book, held, bid + 10

    def assert_sliced(self, book, sells, ask, agent):
        self.assertEqual(len(sells), 3)
        for order in sells:
            self.assertEqual(order.purpose, "exit")
            self.assertLessEqual(order.quantity * ask * GATEWAY_MARKET_MARKUP, CAP)
        self.assertEqual(len({order.id for order in sells}), 3)
        self.assertNotIn(self.btc.key, book.account(agent.id).holdings)
        self.assertTrue(book.reconcile().ok)
        self.assertTrue(book.evidence_integrity(agent.id)["ok"])

    def test_an_agents_own_exit_of_a_swing_sized_position_goes_in_slices(self):
        agent = self.seated()
        book, held, ask = self.hold(agent)
        before = len(self.broker.submitted)
        woke = self.house.wake(agent)
        self.assertEqual([i.side for i in woke["intents"]], ["sell"])
        outcomes = self.house._submit_wakes("alpaca-paper", [woke])
        self.assertEqual([o.status for o in outcomes], ["filled"], [o.detail for o in outcomes])
        self.assert_sliced(book, self.broker.submitted[before:], ask, agent)

    def test_a_dead_agents_swing_sized_position_is_wound_down_in_slices(self):
        agent = self.seated()
        book, held, ask = self.hold(agent)
        before = len(self.broker.submitted)
        self.house.kill(self.house.registry.get(agent.id), "test", "a test death")
        self.assert_sliced(book, self.broker.submitted[before:], ask, agent)
        self.assertTrue(book.account(agent.id).swept)  # flat, so its cash went back


if __name__ == "__main__":
    unittest.main()

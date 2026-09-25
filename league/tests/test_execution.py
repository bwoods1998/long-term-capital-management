"""Execution (workstream X of the forward-first run, Sept 25, 2026).

X1: every snapshot carries the agent's own fill rate and median time to fill on its venue's real book
(`league/execution.py`), and the research brief asks for a requote rule where that rate is under 25% on at
least five finished orders. At T0 the crypto-alts probes filled 0-18% of their real bids (haghani-56 2 of 23)
and nothing told them.

X3: a refused entry's cap says, after `book.FIT_MARK`, the band it was judged in, the cap and the room left, so
the next order fits; the rule's own text before the mark is unchanged. At 10:36Z Sept 25, 84 real entries a day
were refused "insufficient desk cash" with no rule named and no word that nothing fits under Alpaca's $10 minimum.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument

from league import execution
from league.book import FIT_MARK, Book, Limits
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_book import BookCase
from league.tests.test_house import HouseCase
from league.tests.test_real_entry_rules import RealEntryCase, rules
from league.tests.test_researcher import ResearchCase

D = Decimal
MINUTE = 60.0


class Orders:
    """Order and fill rows written as the book writes them: a House order with the agents' shares, its status rows,
    and each agent's own venue fill."""

    def __init__(self, ledger, clock):
        self.ledger, self.clock, self.n = ledger, clock, 0

    def place(self, *agents, book="alpaca", side="buy"):
        self.n += 1
        order_id = f"ord-{self.n}"
        self.status(order_id, "new", *agents, book=book, side=side)
        return order_id

    def status(self, order_id, status, *agents, book="alpaca", side="buy"):
        self.ledger.append("book.order", {"book": book, "order_id": order_id, "side": side, "status": status,
                                          "shares": [{"agent": a, "intent_id": f"in-{order_id}-{a}", "quantity": "1"} for a in agents]},
                           agent="house")

    def fill(self, agent, order_id, book="alpaca", side="buy"):
        self.ledger.append("book.fill", {"book": book, "order_id": order_id, "side": side, "source": "venue", "quantity": "1"},
                           agent=agent)


class FillStatsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.orders = Orders(self.ledger, self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def stats(self, agent="a1", book="alpaca"):
        return execution.fill_stats(self.ledger, agent, book, self.clock())

    def test_filled_unfilled_resting_and_the_times(self):
        o = self.orders
        old = o.place("a1")  # eight days before the rest: outside the week
        o.fill("a1", old)
        self.clock.advance(8 * 86400)
        filled = o.place("a1")
        cancelled = o.place("a1")
        rejected = o.place("a1")
        resting = o.place("a1")
        sold = o.place("a1", side="sell")
        shared = o.place("a1", "b1")  # a House order two agents have a share of: each fill is its own
        o.status(rejected, "rejected", "a1")  # the venue refused it: not a question of price
        self.clock.advance(2 * MINUTE)
        o.fill("a1", sold, side="sell")
        o.fill("b1", shared)
        self.clock.advance(4 * MINUTE)
        o.fill("a1", filled)
        o.status(filled, "filled", "a1")
        self.clock.advance(34 * MINUTE)
        o.status(cancelled, "cancelled", "a1")
        o.status(shared, "cancelled", "a1", "b1")
        o.status(resting, "accepted", "a1")
        s = self.stats()
        self.assertEqual((s["orders"], s["filled"], s["unfilled"], s["resting"]), (5, 2, 2, 1))
        self.assertEqual(s["fill_rate"], 0.5)
        self.assertEqual(s["median_minutes_to_fill"], 4.0)  # 6 and 2 minutes
        self.assertEqual(s["median_minutes_unfilled"], 40.0)
        self.assertEqual(s["entries"], {"orders": 4, "filled": 1, "unfilled": 2, "resting": 1, "fill_rate": round(1 / 3, 4)})
        b1 = self.stats("b1")
        self.assertEqual((b1["filled"], b1["unfilled"], b1["fill_rate"]), (1, 0, 1.0))
        self.assertEqual(self.stats(book="kalshi")["orders"], 0)
        self.assertIsNone(self.stats(book="kalshi")["fill_rate"])

    def test_the_index_reads_only_what_is_new_and_a_late_fill_counts(self):
        o = self.orders
        first = o.place("a1")
        o.status(first, "cancelled", "a1")
        self.assertEqual(self.stats()["unfilled"], 1)
        index = execution._index(self.ledger)
        cursor = index.cursor
        o.fill("a1", first)  # a partial fill the venue reports after the cancel: it did fill
        s = self.stats()
        self.assertGreater(index.cursor, cursor)
        self.assertIs(execution._index(self.ledger), index, "one index a ledger")
        self.assertEqual((s["filled"], s["unfilled"]), (1, 0))

    def test_a_requote_is_asked_under_a_quarter_on_five_finished_orders(self):
        self.assertFalse(execution.needs_requote(None))
        self.assertFalse(execution.needs_requote({"filled": 0, "unfilled": 4, "fill_rate": 0.0}), "0 of 4 is a question")
        self.assertTrue(execution.needs_requote({"filled": 1, "unfilled": 4, "fill_rate": 0.2}))
        self.assertFalse(execution.needs_requote({"filled": 2, "unfilled": 6, "fill_rate": 0.25}))
        self.assertEqual(execution.real_fill_stats(self.ledger, "a1", "kalshi", self.clock())["book"], "kalshi")
        self.assertIsNone(execution.real_fill_stats(self.ledger, "a1", "coinbase", self.clock()))


class SnapshotCarriesExecutionTest(HouseCase):
    def test_every_snapshot_carries_its_own_real_and_practice_fill_rates(self):
        agent = self.seated()
        o = Orders(self.house.ledger, self.clock)
        for _ in range(3):
            o.status(o.place(agent.id), "cancelled", agent.id)
        o.fill(agent.id, o.place(agent.id))
        o.fill(agent.id, o.place(agent.id, book="alpaca-paper"), book="alpaca-paper")
        o.status(o.place("someone-else"), "cancelled", "someone-else")
        ctx = self.house.snapshot(agent, self.house.books["alpaca-paper"])
        real = ctx["execution"]["real"]
        self.assertEqual((real["book"], real["orders"], real["filled"], real["unfilled"], real["fill_rate"]), ("alpaca", 4, 1, 3, 0.25))
        self.assertEqual((ctx["execution"]["practice"]["book"], ctx["execution"]["practice"]["filled"]), ("alpaca-paper", 1))


class ResearchBriefAsksForARequoteTest(ResearchCase):
    def orders(self, agent, filled, unfilled):
        o = Orders(self.ledger, self.clock)
        for i in range(filled + unfilled):
            order_id = o.place(agent.id, book="kalshi")
            if i < filled:
                o.fill(agent.id, order_id, book="kalshi")
            else:
                o.status(order_id, "cancelled", agent.id, book="kalshi")

    def test_under_a_quarter_on_five_finished_orders_the_brief_asks_for_a_requote_rule(self):
        self.orders(self.parent, 1, 5)
        self.researcher([]).research(self.parent, {}, session="s1")
        prompt = self.first_prompt()
        self.assertIn("YOUR REAL EXECUTION (the kalshi book", prompt)
        self.assertIn("1 of 6 finished orders filled (17%)", prompt)
        self.assertIn("REQUOTE:", prompt)
        self.assertIn("probe_may_take", prompt)  # a Kalshi probe may take the price (M2)
        self.assertLess(prompt.index("THIS PASS"), prompt.index("REQUOTE:"), "after the cached prefix")

    def test_a_rate_over_a_quarter_is_shown_and_asks_nothing(self):
        self.orders(self.child, 4, 1)
        self.researcher([]).research(self.child, {}, session="s1")
        self.assertIn("4 of 5 finished orders filled (80%)", self.first_prompt())
        self.assertNotIn("REQUOTE:", self.first_prompt())

    def test_no_real_order_no_execution_line(self):
        self.researcher([]).research(self.parent, {}, session="s1")
        self.assertNotIn("YOUR REAL EXECUTION", self.first_prompt())


def crypto(symbol="AVAX/USD", venue="alpaca"):
    return Instrument("crypto", symbol.replace("/", "-"), venue, market_id=symbol)


class RefusalsSayWhatFitsTest(RealEntryCase):
    """X3 on a real Kalshi book (the allocator's word for the band is `family_taker`'s)."""

    taker_record = {"family": "fav", "positive": False, "may_take": False, "n": 0, "bound": None, "band": "probe"}

    def test_the_event_cap_names_the_band_the_cap_and_how_many_contracts_fit(self):
        game = "KXBTCD-26SEP2501"
        self.seat("hilibrand-x", usd="12", position="6", order="6")
        for strike in ("T84399.99", "T84499.99"):
            self.quote(f"{game}-{strike}", "0.93", "0.95")
        with rules("max_event_share"):
            self.assertEqual(self.bid("hilibrand-x", f"{game}-T84399.99", "2", "0.94").status, "resting")  # $1.88
            out = self.bid("hilibrand-x", f"{game}-T84499.99", "2", "0.94")  # $3.76 > $3.00
        self.assertEqual(out.status, "refused")
        before, _, after = out.detail.partition(FIT_MARK)
        self.assertEqual(before, f"one event may hold at most 25% of the stake: {game} would hold $3.76 of this account's $12.00 "
                                 "(holdings at cost, working buys on every market of the event, and this order; "
                                 "constitution allocator.max_event_share)")
        self.assertEqual(after, " as a probe on the kalshi book: the cap on this event is $3.00, $1.88 of it is held or working, "
                                "so at most 1 contract at 0.94 fits")


class CashRefusalsSayWhatFitsTest(BookCase):
    venue, family, real, cash = "alpaca", "alpaca", True, "1000"

    def new_book(self):
        return Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=True, clock=self.clock,
                    family_taker=lambda agent: {"band": "probe"})

    def test_insufficient_cash_names_its_rule_and_that_nothing_fits_under_the_venue_minimum(self):
        """haghani-56, Sept 24: a $12.01 AVAX/USD bid against $0.35 free, refused 83 times in a day."""
        self.book.reconcile()
        self.seat("whale", usd="600")
        self.seat("haghani-56", usd="0.35", position="12.5", order="12.5")
        self.broker.set_quote(crypto(), "24.00", "24.02")
        reasons = self.book.check(self.intent("haghani-56", crypto(), "buy", "0.5", order_type="limit", limit_price="24.02"),
                                  self.book._quote(crypto()), "2026-09-25T04:00:00.000Z")
        cash = next(r for r in reasons if r.startswith("insufficient desk cash"))
        self.assertEqual(cash.split(FIT_MARK)[0], "insufficient desk cash: need 12.01, have 0.35")
        self.assertIn(f"{FIT_MARK} as a probe on the alpaca book", "; ".join(reasons))
        self.assertIn("ltcm/risk.py rule_cash", cash)
        self.assertIn("$0.35 is free", cash)
        book_cash = next(r for r in reasons if r.startswith("needs $"))
        self.assertIn("under the venue's $10 minimum for AVAX/USD: nothing more fits", book_cash)
        self.assertEqual(sum(1 for r in reasons if "as a probe" in r), 1, "the band once in the joined text")

    def test_a_practice_book_names_practice_and_exits_are_never_annotated(self):
        book = Book("alpaca-paper", FakeBroker("alpaca-paper"), self.ledger, fees=Fees("alpaca"), real_money=False, clock=self.clock)
        book.limits["a1"] = Limits(D("100"), D("75"))
        book.stake("a1", "200")
        book.broker.set_quote(crypto(venue="alpaca-paper"), "24.00", "24.02")
        big = self.intent("a1", crypto(venue="alpaca-paper"), "buy", "10", order_type="limit", limit_price="24.02")
        reasons = book.check(big, book._quote(big.instrument), "2026-09-25T04:00:00.000Z")
        rung = next(r for r in reasons if "this rung's" in r and r.startswith("order of"))
        self.assertIn(f"{FIT_MARK} in practice on the alpaca-paper book", " ".join(reasons))
        self.assertIn("so an order of at most $75.00 fits", rung)
        sell = self.intent("a1", crypto(venue="alpaca-paper"), "sell", "10", order_type="limit", limit_price="24.00")
        self.assertFalse([r for r in book.check(sell, book._quote(sell.instrument), "2026-09-25T04:00:00.000Z") if FIT_MARK in r])


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument, UnknownOutcome

from league.book import Book, BookError, Intent, Limits, allocate, market_key, yes_space
from league.fees import Fees
from league.ledger import HOUSE, Ledger
from league.tests.fakes import Clock, FakeBroker, iso

D = Decimal
BTC = Instrument("crypto", "BTC-USD", "alpaca-paper", market_id="BTC/USD")
SPY = Instrument("equity", "SPY", "alpaca-paper")


def event(leg="yes", ticker="KXBTCD-26SEP2017-T80999", venue="kalshi"):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


class BookCase(unittest.TestCase):
    venue = "alpaca-paper"
    family = "alpaca"
    real = False
    cash = "100000"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.broker = FakeBroker(self.venue, cash=self.cash, family=self.family)
        self.book = self.new_book()
        self.n = 0

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def new_book(self):
        return Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=self.real, clock=self.clock)

    def seat(self, agent, usd="200", position="100", order="75"):
        self.book.limits[agent] = Limits(D(position), D(order))
        if usd:
            self.book.stake(agent, usd)

    def intent(self, agent, instrument, side, quantity, **kw):
        self.n += 1
        return Intent.new(
            agent=agent, instrument=instrument, side=side, quantity=quantity,
            reason=kw.pop("reason", f"test {self.n}"), created_at=iso(self.clock), nonce=str(self.n), **kw,
        )


class AllocateTest(unittest.TestCase):
    def test_pro_rata_on_a_whole_contract_grid(self):
        self.assertEqual(allocate(D(4), [D(3), D(2)], D(1)), [D(2), D(2)])
        self.assertEqual(allocate(D(1), [D(3), D(2)], D(1)), [D(1), D(0)])
        self.assertEqual(sum(allocate(D(7), [D(5), D(5), D(5)], D(1))), D(7))

    def test_never_more_than_asked_and_never_more_than_there_is(self):
        self.assertEqual(allocate(D(10), [D(3), D(2)], D(1)), [D(3), D(2)])
        self.assertEqual(allocate(D(0), [D(3)], D(1)), [D(0)])
        parts = allocate(D("0.000000005"), [D("0.000000003"), D("0.000000004")], D("0.000000001"))
        self.assertEqual(sum(parts), D("0.000000005"))
        self.assertTrue(all(p <= w for p, w in zip(parts, [D("0.000000003"), D("0.000000004")])))

    def test_fractional_split_sums_exactly(self):
        parts = allocate(D("0.0007"), [D("0.0005"), D("0.0004"), D("0.0001")], D("0.000000001"))
        self.assertEqual(sum(parts), D("0.0007"))


class YesSpaceTest(unittest.TestCase):
    def test_a_no_bid_is_a_yes_offer_at_the_complement(self):
        self.assertEqual(yes_space(event("no"), "buy", D("0.40")), ("sell", D("0.60")))
        self.assertEqual(yes_space(event("yes"), "buy", D("0.40")), ("buy", D("0.40")))
        self.assertEqual(market_key(event("no")), market_key(event("yes")))


class PaperBookTest(BookCase):
    def test_no_seat_no_trade(self):
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.assertEqual(out[0].status, "refused")
        self.assertIn("no seat", out[0].detail)

    def test_market_buy_is_attributed_with_the_in_kind_fee_and_reconciles(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", reason="momentum")])
        self.assertEqual(out[0].status, "filled")
        account = self.book.account("a1")
        holding = account.holdings[BTC.key]
        self.assertEqual(holding.quantity, D("0.00049875"))  # 0.25% of the coins went to the venue
        self.assertEqual(account.cash, D("200") - D("0.0005") * D("80010"))
        self.assertEqual(holding.reason, "momentum")
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(self.book.baseline_cash, D("100000"))

    def test_sell_pays_the_fee_from_proceeds_and_realizes_pnl(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.broker.set_quote(BTC, "82000", "82010")
        out = self.book.submit([self.intent("a1", BTC, "sell", "0.00049875")])
        self.assertEqual(out[0].status, "filled")
        account = self.book.account("a1")
        self.assertEqual(account.holdings, {})
        proceeds = D("0.00049875") * D("82000")
        fee = D("0.11")  # 0.25% of 40.8975, rounded up to the cent
        self.assertEqual(account.cash, D("200") - D("40.005") + proceeds - fee)
        self.assertEqual(account.realized, proceeds - fee - D("40.005"))
        self.assertTrue(self.book.reconcile().ok)

    def test_opposite_market_orders_cross_inside_the_house(self):
        self.seat("buyer")
        self.seat("seller")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("seller", BTC, "buy", "0.0006")])
        sent_before = len(self.broker.submitted)
        held = self.book.account("seller").holdings[BTC.key].quantity
        out = self.book.submit([
            self.intent("buyer", BTC, "buy", "0.0005"),
            self.intent("seller", BTC, "sell", str(held)),
        ])
        by = {o.agent: o for o in out}
        self.assertEqual(by["buyer"].status, "crossed")
        # The seller had more to sell than the buyer wanted: only the difference reached the venue.
        self.assertEqual(len(self.broker.submitted) - sent_before, 1)
        self.assertEqual(self.broker.submitted[-1].side, "sell")
        self.assertEqual(self.broker.submitted[-1].quantity, held - D("0.0005"))
        buyer = self.book.account("buyer")
        self.assertEqual(buyer.cash, D("200") - D("0.0005") * D("80010"))  # paid the ask, as alone
        self.assertEqual(buyer.holdings[BTC.key].quantity, D("0.00049875"))  # and the fee
        self.assertEqual(self.book.account("seller").holdings, {})
        house = self.book.account(HOUSE)
        self.assertGreater(house.cash, 0)  # the spread and fees the account never paid
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)

    def test_partial_fill_is_split_pro_rata(self):
        self.seat("a1")
        self.seat("a2")
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.fill_fraction = D("0.5")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0006"), self.intent("a2", BTC, "buy", "0.0002")])
        self.assertEqual({o.status for o in out}, {"partial"})
        self.assertEqual(len(self.broker.submitted), 1)
        q1 = self.book.account("a1").holdings[BTC.key].quantity
        q2 = self.book.account("a2").holdings[BTC.key].quantity
        self.assertAlmostEqual(float(q1 / q2), 3.0, places=4)
        self.assertTrue(self.book.reconcile().ok)

    def test_no_shorts_no_leverage_and_the_order_cap(self):
        self.seat("a1", usd="50", position="1000", order="1000")
        self.broker.set_quote(BTC, "80000", "80010")
        short = self.book.submit([self.intent("a1", BTC, "sell", "0.0001")])[0]
        self.assertEqual(short.status, "refused")
        levered = self.book.submit([self.intent("a1", BTC, "buy", "0.0007")])[0]  # $56 on $50
        self.assertEqual(levered.status, "refused")
        self.assertIn("free cash", levered.detail)
        self.seat("rich", usd="5000", position="5000", order="5000")
        capped = self.book.submit([self.intent("rich", BTC, "buy", "0.001")])[0]  # $80
        self.assertEqual(capped.status, "refused")
        self.assertIn("$75 order cap", capped.detail)

    def test_rung_limits_bind(self):
        self.seat("a1", usd="200", position="10", order="10")
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0002")])[0]  # $16
        self.assertEqual(out.status, "refused")
        self.assertIn("this rung", out.detail)
        ok = self.book.submit([self.intent("a1", BTC, "buy", "0.0001")])[0]
        self.assertEqual(ok.status, "filled")
        again = self.book.submit([self.intent("a1", BTC, "buy", "0.0001")])[0]  # would hold $16
        self.assertEqual(again.status, "refused")

    def test_whole_shares_for_an_equity_limit_order(self):
        self.seat("a1")
        self.broker.set_quote(SPY, "50.00", "50.02")
        bad = self.book.submit([self.intent("a1", SPY, "buy", "0.5", order_type="limit", limit_price="49.90")])[0]
        self.assertEqual(bad.status, "refused")
        good = self.book.submit([self.intent("a1", SPY, "buy", "1", order_type="limit", limit_price="49.90")])[0]
        self.assertEqual(good.status, "resting")

    def test_a_resting_order_blocks_an_order_that_would_hit_it(self):
        self.seat("maker")
        self.seat("taker")
        self.broker.set_quote(SPY, "50.00", "50.02")
        self.book.submit([self.intent("taker", SPY, "buy", "1")])
        self.assertEqual(self.book.submit([self.intent("maker", SPY, "buy", "1", order_type="limit", limit_price="50.00")])[0].status, "resting")
        hit = self.book.submit([self.intent("taker", SPY, "sell", "1")])[0]
        self.assertEqual(hit.status, "refused")
        self.assertIn("own resting order", hit.detail)
        above = self.book.submit([self.intent("taker", SPY, "sell", "1", order_type="limit", limit_price="50.05")])[0]
        self.assertEqual(above.status, "resting")

    def test_a_resting_fill_arrives_on_a_later_poll_as_a_maker(self):
        self.book.reconcile()  # the House opens every book's baseline before anything trades
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.assertEqual(out.status, "resting")
        self.assertEqual(self.book.account("a1").holdings, {})
        self.broker.fill_resting(out.order_id, "0.0005")
        self.book.poll()
        holding = self.book.account("a1").holdings[BTC.key]
        # Alpaca reports no fee, so the book assumes the taker's 0.25%; the venue charged a maker's
        # 0.15%. Reconciliation finds the extra coins, inside the known allowance, for the House.
        self.assertEqual(holding.quantity, D("0.0005") - D("0.00000125"))
        self.assertEqual(self.book.open_orders("a1"), [])
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(self.book.account(HOUSE).holdings[BTC.key].quantity, D("0.0000005"))
        self.assertTrue(self.book.reconcile().ok)

    def test_reserved_cash_counts_against_the_next_order(self):
        self.seat("a1", usd="90")
        self.broker.set_quote(BTC, "80000", "80010")
        resting = [
            self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
            for _ in range(2)
        ]
        self.assertEqual([o.status for o in resting], ["resting", "resting"])  # $79 of the $90 is spoken for
        third = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.assertEqual(third.status, "refused")
        self.assertIn("free cash", third.detail)
        self.assertEqual(self.book.cancel("a1", resting[0].order_id).status, "cancelled")
        fourth = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.assertEqual(fourth.status, "resting")

    def test_a_restart_rebuilds_the_same_book(self):
        self.seat("a1")
        self.seat("a2")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005"), self.intent("a2", BTC, "buy", "0.0003")])
        self.book.submit([self.intent("a2", BTC, "buy", "0.0002", order_type="limit", limit_price="79000")])
        self.book.reconcile()
        again = self.new_book()
        for agent in ("a1", "a2", HOUSE):
            a, b = self.book.account(agent), again.account(agent)
            self.assertEqual((a.cash, a.staked, a.realized, a.fees), (b.cash, b.staked, b.realized, b.fees))
            self.assertEqual({k: (h.quantity, h.cost) for k, h in a.holdings.items()}, {k: (h.quantity, h.cost) for k, h in b.holdings.items()})
        self.assertEqual(len(again.open_orders()), 1)
        self.assertEqual(again.baseline_cash, self.book.baseline_cash)
        again.limits = dict(self.book.limits)
        self.assertTrue(again.reconcile().ok)

    def test_a_repeated_intent_is_not_traded_twice(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        intent = self.intent("a1", BTC, "buy", "0.0005")
        self.book.submit([intent])
        self.assertEqual(self.book.submit([intent])[0].status, "duplicate")
        self.assertEqual(len(self.broker.submitted), 1)

    def test_a_lost_answer_is_resolved_by_the_next_poll(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.lose_next_submit = True
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        self.assertEqual(out.status, "unknown")
        self.assertFalse(self.book.reconcile().ok)  # an unknown order is not a reconciled book
        self.book.poll()
        self.assertEqual(self.book.open_orders(), [])
        self.assertEqual(self.book.account("a1").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_a_mismatch_freezes_entries_but_not_exits(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("5")  # money moved that the ledger cannot explain
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertEqual(result.cash_diff, D("-5"))
        buy = self.book.submit([self.intent("a1", BTC, "buy", "0.0001")])[0]
        self.assertEqual(buy.status, "refused")
        self.assertIn("frozen", buy.detail)
        sell = self.book.submit([self.intent("a1", BTC, "sell", "0.0001")])[0]
        self.assertEqual(sell.status, "filled")
        self.book.adjust_baseline("-5", "owner withdrawal confirmed by the venue's activity record")
        self.assertTrue(self.book.reconcile().ok)

    def test_sub_cent_drift_is_booked_as_dust(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.004")
        result = self.book.reconcile()
        self.assertTrue(result.ok)
        self.assertEqual(result.dust_booked, D("-0.004"))
        self.assertEqual(self.book.reconcile().cash_diff, D("0"))

    def test_alpacas_habits_are_handled(self):
        """Measured on the paper account on Sept 19, 2026: a market order comes back `accepted`
        and fills a moment later, still as a taker, and the position is reported as BTCUSD."""
        self.broker.asynchronous = True
        self.broker.rename_crypto = True
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        self.assertEqual(out.status, "sent")
        self.book.poll()
        self.assertEqual(self.book.account("a1").holdings[BTC.key].quantity, D("0.00049875"))  # taker, not maker
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)

    def test_a_position_shortfall_under_a_cent_comes_off_the_holder(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.assertTrue(self.book.reconcile().ok)
        inst, held = self.broker.held[BTC.key]
        self.broker.held[BTC.key] = (inst, held - D("0.00000001"))  # the venue rounded its fee up
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.account("a1").holdings[BTC.key].quantity, D("0.00049874"))
        self.broker.held[BTC.key] = (inst, held - D("0.0001"))  # $8 missing is not dust
        self.assertFalse(self.book.reconcile().ok)

    def test_a_crumb_left_at_the_venue_after_the_holder_sold_out_is_dust_not_a_freeze(self):
        """Found by the ladder test: after thousands of round trips the venue showed 0.000000001
        BTC that no agent held any more, and with no holder there was no instrument to value it
        against, so reconciliation called it a real difference and froze the book."""
        self.book.reconcile()
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        held = self.book.account("a1").holdings[BTC.key].quantity
        self.book.submit([self.intent("a1", BTC, "sell", str(held))])
        self.assertEqual(self.book.account("a1").holdings, {})
        inst, _ = self.broker.held[BTC.key]
        self.broker.held[BTC.key] = (inst, D("0.000000001"))
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(self.book.frozen)
        self.assertEqual(self.book.account(HOUSE).holdings[BTC.key].quantity, D("0.000000001"))
        again = self.new_book()  # and a restart knows the instrument too
        self.assertTrue(again.reconcile().ok)

    def test_cash_reserved_behind_a_resting_crypto_bid_is_not_missing_cash(self):
        """Measured on the paper account: two resting $40 crypto bids took exactly $80.00 out of the
        venue's `cash`. It comes back on a cancel and turns into coins on a fill."""
        self.broker.reserve_open_buys = True
        self.book.reconcile()
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        rest = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.assertEqual(rest.status, "resting")
        self.assertEqual(self.broker.balance().cash, D("100000") - D("39.5"))
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.book.cancel("a1", rest.order_id)
        self.assertTrue(self.book.reconcile().ok)
        again = self.book.submit([self.intent("a1", BTC, "buy", "0.0005", order_type="limit", limit_price="79000")])[0]
        self.broker.fill_resting(again.order_id, "0.0005")
        self.book.poll()
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)

    def test_the_ledger_verifies_after_all_of_it(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.book.mark()
        self.book.reconcile()
        self.assertGreater(self.ledger.verify(), 5)


class KalshiBookTest(BookCase):
    venue = "kalshi"
    family = "kalshi"
    real = True
    cash = "500"

    def test_a_real_stake_is_a_slice_of_real_cash(self):
        self.book.limits["a1"] = Limits(D(10), D(10))
        with self.assertRaises(BookError):
            self.book.stake("a1", "10")  # not reconciled yet
        self.book.reconcile()
        self.book.stake("a1", "400")
        with self.assertRaises(BookError):
            self.book.stake("a2", "101")

    def test_no_cheap_longshots_and_whole_contracts(self):
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.broker.set_quote(event(), "0.08", "0.10")
        cheap = self.book.submit([self.intent("a1", event(), "buy", "5", order_type="limit", limit_price="0.09", post_only=True)])[0]
        self.assertEqual(cheap.status, "refused")
        self.broker.set_quote(event(), "0.92", "0.94")
        half = self.book.submit([self.intent("a1", event(), "buy", "1.5", order_type="limit", limit_price="0.92", post_only=True)])[0]
        self.assertEqual(half.status, "refused")

    def test_a_no_bid_that_would_lift_our_own_yes_bid_is_refused(self):
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.seat("a2", usd="100", position="50", order="50")
        self.broker.set_quote(event("yes"), "0.60", "0.62")
        self.broker.set_quote(event("no"), "0.38", "0.40")
        rest = self.book.submit([self.intent("a1", event("yes"), "buy", "5", order_type="limit", limit_price="0.60", post_only=True)])[0]
        self.assertEqual(rest.status, "resting")
        cross = self.book.submit([self.intent("a2", event("no"), "buy", "5", order_type="limit", limit_price="0.40")])[0]
        self.assertEqual(cross.status, "refused")
        clear = self.book.submit([self.intent("a2", event("no"), "buy", "5", order_type="limit", limit_price="0.39", post_only=True)])[0]
        self.assertEqual(clear.status, "refused")  # one account never holds both legs of a market
        self.assertIn("cannot hold both", clear.detail)

    def test_a_no_holding_reported_as_a_negative_count_reconciles(self):
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.broker.set_quote(event("no"), "0.90", "0.92")
        out = self.book.submit([self.intent("a1", event("no"), "buy", "5")])[0]
        self.assertEqual(out.status, "filled")
        inst, held = self.broker.held.pop(event("no").key)
        bare = Instrument("event", inst.symbol, inst.venue, market_id=inst.market_id)  # as the real adapter reports it
        self.broker.held[bare.key] = (bare, -held)
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)

    def test_maker_fill_then_settlement_pays_the_winning_leg(self):
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.broker.set_quote(event(), "0.92", "0.94")
        rest = self.book.submit([self.intent("a1", event(), "buy", "10", order_type="limit", limit_price="0.92", post_only=True, reason="favorite")])[0]
        self.broker.fill_resting(rest.order_id, "10")
        self.book.poll()
        account = self.book.account("a1")
        self.assertEqual(account.cash, D("100") - D("9.20"))  # a maker pays no fee on this series
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.settle(event().market_id, "yes"), 1)
        self.assertEqual(account.cash, D("100.80"))
        self.assertEqual(account.realized, D("0.80"))
        self.assertEqual(account.holdings, {})

    def test_the_venues_own_fee_is_what_a_real_kalshi_fill_pays(self):
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.broker.set_quote(event(), "0.50", "0.52")
        out = self.book.submit([self.intent("a1", event(), "buy", "10")])[0]
        self.assertEqual(out.status, "filled")
        fee = self.broker.orders[out.order_id].fees
        self.assertGreater(fee, 0)
        self.assertEqual(self.book.account("a1").cash, D("100") - D("5.20") - fee)
        self.assertTrue(self.book.reconcile().ok)


if __name__ == "__main__":
    unittest.main()

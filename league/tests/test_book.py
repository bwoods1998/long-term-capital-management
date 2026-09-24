import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ltcm.broker import Instrument, UnknownOutcome, VenueUnavailable

from league.book import Book, BookError, Intent, Limits, allocate, market_key, yes_space
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.ledger import HOUSE, Ledger
from league.tests.fakes import Clock, FakeBroker, iso, without_real_entry_rules

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
        # These tests are about the book, not the real book's entry rules (X0), which a test opts into.
        # Undone by tearDown, which the cases built by hand call, and by a cleanup should setUp fail.
        self._entry_rules = without_real_entry_rules()
        self._entry_rules.start()
        self.addCleanup(self._restore_entry_rules)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.broker = FakeBroker(self.venue, cash=self.cash, family=self.family)
        self.book = self.new_book()
        self.n = 0

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()
        self._restore_entry_rules()

    def _restore_entry_rules(self):
        patcher, self._entry_rules = getattr(self, "_entry_rules", None), None
        if patcher is not None:
            patcher.stop()

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
    def test_paper_adoption_cannot_mask_missing_owned_units_with_a_negative_baseline(self):
        self.seat('owner')
        self.broker.set_quote(BTC, '80000', '80010')
        self.book.reconcile()
        self.book.submit([self.intent('owner', BTC, 'buy', '0.0005')])
        self.book.reconcile()
        self.broker.held.pop(BTC.key)  # venue execution whose attribution is absent
        for _ in range(6):
            self.assertFalse(self.book.reconcile().ok)
        self.assertNotIn(BTC.key, self.book.baseline_positions)
        self.assertFalse(any('adopted' in e.payload['note'] for e in self.ledger.iter(kinds='book.baseline')))

    def test_legacy_negative_baseline_taints_only_its_holders_and_cannot_be_laundered(self):
        self.seat('owner'); self.seat('clean')
        self.broker.set_quote(BTC, '80000', '80010')
        self.book.reconcile()
        self.book.submit([self.intent('owner', BTC, 'buy', '0.0005')])
        held = self.book.account('owner').holdings[BTC.key].quantity
        self.broker.held.pop(BTC.key)
        key = next(iter(self.book._ledger_totals()[1]))
        self.book._baseline_row(self.book.baseline_cash, {key: -held}, 'legacy masking adjustment')
        self.assertTrue(self.book.reconcile().ok)  # aggregate alone is not attribution proof
        self.assertFalse(self.book.evidence_integrity('owner')['ok'])
        self.assertTrue(self.book.evidence_integrity('clean')['ok'])
        self.book._baseline_row(self.book.baseline_cash, {}, 'a later rewrite cannot repair past marks')
        restored = self.new_book()
        self.assertFalse(restored.evidence_integrity('owner')['ok'])
        self.assertTrue(restored.evidence_integrity('clean')['ok'])

    def test_funding_history_survives_a_profitable_sweep_and_restart(self):
        self.seat("winner", usd="25")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("winner", BTC, "buy", "0.000124")])
        self.broker.set_quote(BTC, "800000", "800010")
        held = self.book.account("winner").holdings[BTC.key].quantity
        self.book.submit([self.intent("winner", BTC, "sell", held)])
        self.book.stake("winner", -self.book.account("winner").cash, note="account closed")
        account = self.book.account("winner")
        self.assertLess(account.staked, -D(25))
        self.assertEqual(account.cash, D(0))
        self.assertTrue(account.funded)
        self.assertTrue(account.swept)
        self.book = self.new_book()
        self.assertTrue(self.book.account("winner").funded)
        self.assertTrue(self.book.account("winner").swept)
        self.book.stake("winner", "25", note="new trial")
        self.book = self.new_book()
        account = self.book.account("winner")
        self.assertTrue(account.funded)
        self.assertFalse(account.swept)
        self.assertLess(account.staked, D(0))
        self.assertEqual(account.cash, D(25))
        self.assertTrue(self.book.reconcile().ok)

    def test_zero_stake_does_not_record_initial_funding(self):
        self.assertFalse(self.book.account("new").funded)
        self.book.stake("new", "0")
        self.book = self.new_book()
        self.assertFalse(self.book.account("new").funded)
        self.book.stake("new", "25")
        self.assertTrue(self.book.account("new").funded)

    def test_partial_sizing_withdrawal_keeps_the_account_open_after_restart(self):
        self.seat("a1", usd="100")
        self.book.stake("a1", "-75", note="rung 3 sizing")
        self.book = self.new_book()
        self.assertEqual(self.book.account("a1").cash, D(25))
        self.assertFalse(self.book.account("a1").swept)
        self.book.stake("a1", "-25", note="account closed")
        self.book.stake("a1", "0")
        self.book = self.new_book()
        self.assertTrue(self.book.account("a1").swept)
        self.assertTrue(self.book.account("a1").funded)

    def test_withdrawing_free_cash_leaves_holdings_open_for_a_later_sweep(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        self.book.stake("a1", -self.book.account("a1").cash, note="rung 3 sizing")
        self.assertFalse(self.book.account("a1").swept)
        self.assertEqual(self.book.account("a1").cash, D(0))
        held = self.book.account("a1").holdings[BTC.key].quantity
        self.book.submit([self.intent("a1", BTC, "sell", held)])
        self.assertGreater(self.book.account("a1").cash, D(0))
        self.assertFalse(self.book.account("a1").swept)
        self.book.stake("a1", -self.book.account("a1").cash, note="account closed")
        self.assertTrue(self.book.account("a1").swept)
        self.assertTrue(self.book.reconcile().ok)

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

    def test_a_fractional_equity_limit_order_is_a_day_order(self):
        """A7 (Sept 23, 2026): a $25 stock bunt rests a fractional bid at the touch, as a `day` order; a
        limit order was whole shares before, so no bunt could rest a bid on a share over $12.50."""
        self.seat("a1", usd="25", position="12.5", order="12.5")
        self.broker.set_quote(SPY, "49.98", "50.00")
        bid = self.intent("a1", SPY, "buy", "0.25", order_type="limit", limit_price="49.98")  # $12.495 at the bid
        self.assertEqual(bid.time_in_force, "day")
        self.assertEqual(self.book.check(bid, self.broker.quote(SPY), iso(self.clock)), [])
        self.assertEqual(self.book.submit([bid])[0].status, "resting")
        self.assertEqual((self.broker.submitted[-1].quantity, self.broker.submitted[-1].time_in_force), (D("0.25"), "day"))
        gtc = self.intent("a1", SPY, "buy", "0.1", order_type="limit", limit_price="49.90", time_in_force="gtc")
        self.assertIn("a fractional share order must be a day order, not gtc (the venue takes no other)",
                      self.book.check(gtc, self.broker.quote(SPY), iso(self.clock)))
        self.assertEqual(self.book.submit([gtc])[0].status, "refused")
        whole = self.intent("a1", SPY, "buy", "1", order_type="limit", limit_price="49.90", time_in_force="gtc")
        self.assertNotIn("day order", " ".join(self.book.check(whole, self.broker.quote(SPY), iso(self.clock))))  # not the rule
        crypto = self.intent("a1", BTC, "buy", "0.0001", order_type="limit", limit_price="70000", time_in_force="gtc")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertNotIn("day order", " ".join(self.book.check(crypto, self.broker.quote(BTC), iso(self.clock))))

    def test_a_resting_order_blocks_an_entry_that_would_hit_it(self):
        self.seat("maker")
        self.seat("taker")
        self.broker.set_quote(SPY, "50.00", "50.02")
        self.book.submit([self.intent("maker", SPY, "buy", "1")])
        self.assertEqual(self.book.submit([self.intent("maker", SPY, "sell", "1", order_type="limit", limit_price="50.02")])[0].status, "resting")
        hit = self.book.submit([self.intent("taker", SPY, "buy", "1")])[0]
        self.assertEqual(hit.status, "refused")
        self.assertIn("own resting order", hit.detail)
        below = self.book.submit([self.intent("taker", SPY, "buy", "1", order_type="limit", limit_price="49.99")])[0]
        self.assertEqual(below.status, "resting")

    def test_an_exit_that_would_hit_a_resting_bid_is_crossed_inside_the_house(self):
        """D3 (Sept 24, 2026): this sell was refused ("own resting order") and its holder waited; the
        bid is now cancelled at the venue and the two are crossed at its price (test_exit_crossing)."""
        self.book.reconcile()
        self.seat("maker")
        self.seat("taker")
        self.broker.set_quote(SPY, "50.00", "50.02")
        self.book.submit([self.intent("taker", SPY, "buy", "1")])
        self.assertEqual(self.book.submit([self.intent("maker", SPY, "buy", "1", order_type="limit", limit_price="50.00")])[0].status, "resting")
        hit = self.book.submit([self.intent("taker", SPY, "sell", "1")])[0]
        self.assertEqual(hit.status, "crossed", hit.detail)
        self.assertEqual(self.book.account("taker").holdings, {})
        self.assertEqual(self.book.account("maker").holdings[SPY.key].quantity, D("1"))
        self.assertEqual(self.book.account("maker").cash, D("150"))
        self.assertTrue(self.book.reconcile().ok)

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
        self.book.rules["max_position_pct"] = "1"  # isolate cash reservation from the position cap
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

    def test_market_buys_in_one_batch_share_cash_and_position_limits(self):
        self.seat("a1", usd="100", position="50")
        self.broker.set_quote(BTC, "80000", "80010")
        intents = [self.intent("a1", BTC, "buy", "0.0005") for _ in range(3)]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual([outcomes[i.id].status for i in intents], ["filled", "refused", "refused"])
        self.assertGreaterEqual(self.book.account("a1").cash, 0)
        self.assertLessEqual(self.book.account("a1").holdings[BTC.key].cost, 50)

    def test_cross_instrument_market_buys_cannot_spend_the_same_cash(self):
        self.seat("a1", usd="100", position="100")
        instruments = [Instrument("crypto", symbol, self.venue) for symbol in ("BTC/USD", "ETH/USD", "SOL/USD")]
        for instrument in instruments:
            self.broker.set_quote(instrument, "99.99", "100")
        intents = [self.intent("a1", instrument, "buy", "0.4") for instrument in instruments]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual([outcomes[i.id].status for i in intents], ["filled", "filled", "refused"])
        self.assertIn("free cash", outcomes[intents[-1].id].detail)
        self.assertEqual(self.book.account("a1").cash, D("20"))

    def test_a_batch_cannot_sell_the_same_holding_twice(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        held = self.book.account("a1").holdings[BTC.key].quantity
        intents = [self.intent("a1", BTC, "sell", held) for _ in range(2)]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual([outcomes[i.id].status for i in intents], ["filled", "refused"])
        self.assertEqual(self.broker.positions(), [])
        self.assertEqual(self.book.account("a1").holdings, {})

    def test_unfilled_market_orders_keep_their_cash_reserved_after_restart(self):
        self.seat("a1", usd="100", position="100")
        self.broker.asynchronous = True
        instruments = [Instrument("crypto", symbol, self.venue) for symbol in ("BTC/USD", "ETH/USD", "SOL/USD")]
        for instrument in instruments:
            self.broker.set_quote(instrument, "98", "100")
        for instrument in instruments[:2]:
            self.assertEqual(self.book.submit([self.intent("a1", instrument, "buy", "0.4")])[0].status, "sent")
        again = self.new_book()
        again.limits = dict(self.book.limits)
        self.assertEqual(again._reserved_cash("a1"), D("80.4"))
        outcome = again.submit([self.intent("a1", instruments[2], "buy", "0.2")])[0]
        self.assertEqual(outcome.status, "refused")
        self.assertIn("free cash", outcome.detail)

    def test_unfilled_buys_count_against_position_limits(self):
        self.seat("a1", usd="200", position="50")
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.asynchronous = True
        first = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        second = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "refused")
        self.assertIn("working buys", second.detail)

    def test_a_limit_cannot_rest_in_front_of_a_queued_opposite_market_order(self):
        self.seat("buyer")
        self.seat("seller")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("seller", BTC, "buy", "0.0005")])
        held = self.book.account("seller").holdings[BTC.key].quantity
        intents = [self.intent("buyer", BTC, "buy", "0.0005"),
                   self.intent("seller", BTC, "sell", held, order_type="limit", limit_price="80010")]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual(outcomes[intents[0].id].status, "filled")
        self.assertEqual(outcomes[intents[1].id].status, "refused")
        self.assertIn("queued market order", outcomes[intents[1].id].detail)

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

    def test_restart_recovers_a_filled_submit_interrupted_before_attribution(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        with patch.object(self.book, "_attribute", side_effect=RuntimeError("process stopped")):
            with self.assertRaises(RuntimeError):
                self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        again = self.new_book()
        self.assertEqual(again.poll(), 1)
        self.assertEqual(again.account("a1").holdings[BTC.key].quantity, D("0.00049875"))
        self.assertEqual(again.poll(), 0)
        self.assertTrue(again.reconcile().ok)
        self.assertEqual(len(self.broker.submitted), 1)

    def test_restart_recovers_a_terminal_row_written_by_an_older_release(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        with patch.object(self.book, "_attribute", side_effect=RuntimeError("process stopped")):
            with self.assertRaises(RuntimeError):
                self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        working = next(iter(self.book.orders.values()))
        self.book._order_row(self.book._base_of(working), "filled", working.broker_order_id, suffix="old-terminal")
        again = self.new_book()
        self.assertEqual(again.poll(), 1)
        self.assertEqual(again.account("a1").holdings[BTC.key].quantity, D("0.00049875"))
        self.assertEqual(again.open_orders(), [])
        self.assertTrue(again.reconcile().ok)

    def test_restart_finishes_a_pooled_fill_without_attributing_the_first_share_twice(self):
        for agent in ("a1", "a2"):
            self.seat(agent)
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        original = self.book._apply

        def stopped_after_first_fill(kind, agent, payload, at):
            original(kind, agent, payload, at)
            if kind == "book.fill" and payload.get("source") == "venue":
                raise RuntimeError("process stopped after applying one committed fill")

        with patch.object(self.book, "_apply", side_effect=stopped_after_first_fill):
            with self.assertRaises(RuntimeError):
                self.book.submit([self.intent(agent, BTC, "buy", "0.0004") for agent in ("a1", "a2")])
        again = self.new_book()
        self.assertEqual(again.poll(), 1)
        for agent in ("a1", "a2"):
            self.assertEqual(again.account(agent).holdings[BTC.key].quantity, D("0.000399"))
            self.assertEqual(again.account(agent).cash, D("167.996"))
        self.assertEqual(again.poll(), 0)
        self.assertTrue(again.reconcile().ok)

    def test_restart_keeps_a_partial_pooled_fills_original_allocation_and_price(self):
        for agent in ("a1", "a2"):
            self.seat(agent)
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        self.broker.fill_fraction = D("0.5")
        original = self.book._apply

        def stopped_after_first_fill(kind, agent, payload, at):
            original(kind, agent, payload, at)
            if kind == "book.fill" and payload.get("source") == "venue":
                raise RuntimeError("process stopped after applying one committed partial share")

        with patch.object(self.book, "_apply", side_effect=stopped_after_first_fill):
            with self.assertRaises(RuntimeError):
                self.book.submit([self.intent(agent, BTC, "buy", "0.0004") for agent in ("a1", "a2")])
        working = next(iter(self.book.orders.values()))
        # The venue continues trading while the House is down, at a new price.
        order = self.broker.orders[working.order_id]
        self.broker._fill(order, D("0.0004"), D("82000"), "taker")
        self.clock.advance(60)
        again = self.new_book()
        self.assertEqual(again.poll(), 1)
        for agent in ("a1", "a2"):
            self.assertEqual(again.account(agent).holdings[BTC.key].quantity, D("0.000399"))
            self.assertEqual(again.account(agent).cash, D("167.598"))
            fills = list(self.ledger.iter(kinds="book.fill", agent=agent))
            self.assertEqual([row.payload["price"] for row in fills], ["80010", "82000"])
            self.assertEqual([row.at for row in fills], [iso(Clock()), iso(self.clock)])
        self.assertEqual(again.poll(), 0)
        self.assertTrue(again.reconcile().ok)

    def test_a_partial_venue_allocation_recovers_each_transaction_and_memory_failure(self):
        for failure in ("uncommitted", "lost_ack", "applied_first"):
            for restart in (False, True):
                with self.subTest(failure=failure, restart=restart):
                    case = BookCase()
                    case.setUp()
                    try:
                        for agent in ("a1", "a2"):
                            case.seat(agent)
                        case.broker.set_quote(BTC, "80000", "80010")
                        case.book.reconcile()
                        case.broker.fill_fraction = D("0.5")
                        append_one, append_many, apply = case.ledger._append_one, case.ledger.append_many, case.book._apply

                        def interrupted_row(kind, payload, **kwargs):
                            entry = append_one(kind, payload, **kwargs)
                            if kind == "book.fill" and payload.get("source") == "venue":
                                raise RuntimeError("venue allocation transaction interrupted")
                            return entry

                        def lost_ack(rows):
                            entries = append_many(rows)
                            if any(entry.kind == "book.fill" and entry.payload.get("source") == "venue" for entry in entries):
                                raise RuntimeError("committed venue allocation acknowledgement lost")
                            return entries

                        def interrupted_apply(kind, agent, payload, at):
                            apply(kind, agent, payload, at)
                            if kind == "book.fill" and payload.get("source") == "venue":
                                raise RuntimeError("committed venue allocation partially applied")

                        target, name, hook = ((case.ledger, "_append_one", interrupted_row) if failure == "uncommitted" else
                                              (case.ledger, "append_many", lost_ack) if failure == "lost_ack" else
                                              (case.book, "_apply", interrupted_apply))
                        with patch.object(target, name, side_effect=hook):
                            with self.assertRaises(RuntimeError):
                                case.book.submit([case.intent(agent, BTC, "buy", "0.0004") for agent in ("a1", "a2")])
                        self.assertEqual(case.ledger.count(kinds="book.fill"), 0 if failure == "uncommitted" else 2)
                        if restart:
                            case.book = case.new_book()
                        case.book.poll()
                        for agent in ("a1", "a2"):
                            self.assertEqual(case.book.account(agent).cash, D("183.998"))
                            self.assertEqual(case.book.account(agent).holdings[BTC.key].quantity, D("0.0001995"))
                        self.assertEqual(case.ledger.count(kinds="book.fill"), 2)
                        self.assertEqual(len(case.broker.submitted), 1)
                        self.assertTrue(case.book.reconcile().ok)
                    finally:
                        case.tearDown()

    def test_an_allocation_row_committed_before_its_memory_fold_keeps_its_original_timestamp(self):
        for agent in ("a1", "a2"):
            self.seat(agent)
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        self.broker.fill_fraction = D("0.5")
        original = self.book._apply

        def stopped_before_allocation_fold(kind, agent, payload, at):
            if kind == "book.order" and payload.get("allocation"):
                raise RuntimeError("allocation row committed, in-memory fold did not run")
            original(kind, agent, payload, at)

        with patch.object(self.book, "_apply", side_effect=stopped_before_allocation_fold):
            with self.assertRaises(RuntimeError):
                self.book.submit([self.intent(agent, BTC, "buy", "0.0004") for agent in ("a1", "a2")])
        working = next(iter(self.book.orders.values()))
        self.broker._fill(self.broker.orders[working.order_id], D("0.0004"), D("82000"), "taker")
        self.clock.advance(60)
        self.book.poll()  # same process, later time and a newer cumulative venue fill
        for agent in ("a1", "a2"):
            self.assertEqual(self.book.account(agent).cash, D("167.598"))
            fills = list(self.ledger.iter(kinds="book.fill", agent=agent))
            self.assertEqual([row.at for row in fills], [iso(Clock()), iso(self.clock)])
        self.assertTrue(self.book.reconcile().ok)

    def test_an_unpriceable_legacy_buy_blocks_entries_and_cash_withdrawal_but_not_exits(self):
        self.seat("a1")
        self.seat("a2")
        other = Instrument("crypto", "ETH/USD", self.venue)
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.set_quote(other, "99", "100")
        self.book.submit([self.intent("a2", other, "buy", "0.4")])
        self.broker.asynchronous = True
        first = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        self.book.orders[first.order_id].reference_price = None  # legacy row has no stored ask
        self.book.marks.pop(BTC.key)
        self.broker.quotes.pop(BTC.key)
        outcome = self.book.submit([self.intent("a2", other, "buy", "0.1")])[0]
        self.assertEqual(outcome.status, "refused")
        self.assertIn("outstanding buy cannot be priced", outcome.detail)
        with self.assertRaises(BookError):
            self.book.stake("a1", "-1")
        held = self.book.account("a2").holdings[other.key].quantity
        outcome = self.book.submit([self.intent("a2", other, "sell", held)])[0]
        self.assertEqual(outcome.status, "sent")

    def test_a_terminal_response_without_a_fill_price_stays_pollable(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.asynchronous = True
        outcome = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0]
        order = self.broker.get_order(outcome.order_id)
        price, order.average_price = order.average_price, None
        self.book.poll()
        self.assertEqual(len(self.book.open_orders()), 1)
        self.assertEqual(self.book.account("a1").holdings, {})
        order.average_price = price
        self.book.poll()
        self.assertEqual(self.book.open_orders(), [])
        self.assertEqual(self.book.account("a1").holdings[BTC.key].quantity, D("0.00049875"))

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
        self.assertEqual(len(self.book.open_orders()), 1)  # one "no such order" is remembered, not believed (Sept 23, 2026)
        self.clock.advance(61)
        self.book.poll()
        self.assertEqual(self.book.open_orders(), [])
        self.assertEqual(self.book.account("a1").holdings, {})
        self.assertTrue(self.book.reconcile().ok)

    def test_submit_server_errors_and_parse_failures_are_recovered_without_a_second_order(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.reconcile()
        original = self.broker.submit
        for number, error in enumerate((VenueUnavailable("HTTP 502 after upstream timeout"), ValueError("invalid response price")), 1):
            with self.subTest(error=type(error).__name__):
                def accepted_but_response_failed(intent):
                    original(intent)
                    raise error

                with patch.object(self.broker, "submit", side_effect=accepted_but_response_failed):
                    outcome = self.book.submit([self.intent("a1", BTC, "buy", "0.0002")])[0]
                self.assertEqual(outcome.status, "unknown")
                again = self.new_book()
                again.limits = dict(self.book.limits)
                self.assertEqual(again.poll(), 1)
                self.assertEqual(again.account("a1").holdings[BTC.key].quantity, D("0.0001995") * number)
                self.assertEqual(len(self.broker.submitted), number)
                self.assertTrue(again.reconcile().ok)
                self.book = again

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

    def test_orders_left_at_the_venue_by_someone_else_are_cleared_before_a_practice_book_opens(self):
        from ltcm.broker import OrderIntent

        self.broker.set_quote(BTC, "80000", "80010")
        stray = OrderIntent.new(desk_id="an-earlier-house", instrument=BTC, side="buy", quantity="0.0005", order_type="limit", limit_price="79000",
                                time_in_force="gtc", rationale="left behind", created_at=iso(self.clock), nonce="stray")
        self.broker.submit(stray)
        self.assertEqual(len(self.broker.open_orders()), 1)
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.broker.open_orders(), [])

    def test_a_pool_larger_than_the_order_cap_is_sent_as_its_parts(self):
        """Each intent is checked against the $75 cap alone; the gateway checks each ORDER. Three $40
        buys netted into one $120 order would be refused there, so they go as three orders."""
        for agent in ("a1", "a2", "a3"):
            self.seat(agent)
        self.broker.set_quote(BTC, "80000", "80010")
        out = self.book.submit([self.intent(agent, BTC, "buy", "0.0005") for agent in ("a1", "a2", "a3")])
        self.assertEqual([o.status for o in out], ["filled"] * 3)
        self.assertEqual(len(self.broker.submitted), 3)
        self.assertTrue(all(i.quantity * D("80010") <= D("75") for i in self.broker.submitted))
        small = self.book.submit([self.intent(agent, BTC, "buy", "0.0002") for agent in ("a1", "a2")])
        self.assertEqual(len(self.broker.submitted), 4)  # $32 together: still one pooled order
        self.assertTrue(self.book.reconcile().ok)

    def test_every_sell_is_sent_as_an_exit(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
        held = self.book.account("a1").holdings[BTC.key].quantity
        self.book.submit([self.intent("a1", BTC, "sell", str(held))])
        self.assertEqual([i.purpose for i in self.broker.submitted], ["entry", "exit"])

    def test_profitable_micro_exit_above_entry_cap_is_allowed_but_overselling_is_not(self):
        self.seat("a1", usd="25", position="10", order="10")
        self.broker.set_quote(BTC, "79995", "80000")
        self.book.submit([self.intent("a1", BTC, "buy", "0.0001")])
        held = self.book.account("a1").holdings[BTC.key].quantity
        self.broker.set_quote(BTC, "120000", "120010")
        self.assertGreater(held * D("120000"), D("10"))
        self.book.submit([self.intent("a1", BTC, "sell", held * 2)])
        self.assertEqual(len(self.broker.submitted), 1)
        self.assertEqual(self.book.account("a1").holdings[BTC.key].quantity, held)
        self.book.submit([self.intent("a1", BTC, "sell", held)])
        self.assertEqual(self.broker.submitted[-1].purpose, "exit")
        self.assertFalse(self.book.account("a1").holdings)
        self.assertTrue(self.book.reconcile().ok)

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

    def test_restart_requires_a_fresh_reconciliation_before_new_entries(self):
        self.assertEqual(self.book.frozen, 'awaiting startup reconciliation')
        self.book.reconcile()
        self.seat('a1', usd='100', position='50', order='50')
        self.broker.set_quote(event(), '.50', '.52')
        self.book = self.new_book()
        self.book.limits['a1'] = Limits(D(50), D(50))
        out = self.book.submit([self.intent('a1', event(), 'buy', '5')])[0]
        self.assertEqual(out.status, 'refused')
        self.assertIn('startup reconciliation', out.detail)
        self.assertEqual(self.broker.submitted, [])
        self.assertTrue(self.book.reconcile().ok)
        self.assertIsNone(self.book.frozen)
        self.assertEqual(self.book.submit([self.intent('a1', event(), 'buy', '5')])[0].status, 'filled')

    def test_restart_cannot_clear_an_existing_cash_mismatch(self):
        self.book.reconcile()
        self.seat('a1', usd='100', position='50', order='50')
        self.broker.set_quote(event(), '.50', '.52')
        self.book.submit([self.intent('a1', event(), 'buy', '5')])
        self.broker.cash -= D(1)
        self.assertFalse(self.book.reconcile().ok)
        self.book = self.new_book()
        self.book.limits['a1'] = Limits(D(50), D(50))
        self.assertEqual(self.book.submit([self.intent('a1', event(), 'buy', '5')])[0].status, 'refused')
        self.assertFalse(self.book.reconcile().ok)
        self.assertIn('cash differs', self.book.frozen)
        self.broker.cash += D(1)
        self.assertTrue(self.book.reconcile().ok)

    def test_startup_pending_check_still_permits_a_position_reducing_exit(self):
        self.book.reconcile()
        self.seat('a1', usd='100', position='50', order='50')
        self.broker.set_quote(event(), '.50', '.52')
        self.book.submit([self.intent('a1', event(), 'buy', '5')])
        self.book = self.new_book()
        self.book.limits['a1'] = Limits(D(50), D(50))
        self.assertEqual(self.book.submit([self.intent('a1', event(), 'sell', '5')])[0].status, 'filled')
        self.assertEqual(self.book.account('a1').holdings, {})

    def test_a_real_book_will_not_open_over_orders_it_did_not_send(self):
        from ltcm.broker import OrderIntent

        self.broker.set_quote(event(), "0.50", "0.52")
        stray = OrderIntent.new(desk_id="the-owner", instrument=event(), side="buy", quantity="5", order_type="limit", limit_price="0.40",
                                time_in_force="gtc", rationale="the owner's own order", created_at=iso(self.clock), nonce="stray")
        self.broker.submit(stray)
        with self.assertRaises(BookError):
            self.book.reconcile()
        self.assertEqual(len(self.broker.open_orders()), 1)  # never cancelled by the book

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

    def test_a_resting_limit_filled_later_is_booked_as_the_makers_fill_it_was(self):
        """Sept 23, 2026: a Kalshi limit order that rested and was filled later paid no fee (the
        maker's, on most series) and was booked as a taker fill; the auditor read that as an
        unexplained zero-fee taker execution and vetoed the best paper agent."""
        self.book.reconcile()
        self.seat("a1", usd="100", position="50", order="50")
        self.broker.set_quote(event(), "0.49", "0.52")
        out = self.book.submit([self.intent("a1", event(), "buy", "10", order_type="limit", limit_price=D("0.45"))])[0]
        self.assertEqual(out.status, "resting")
        self.broker.fill_resting(out.order_id, "10")
        self.book.poll()
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="a1")][-1]
        self.assertEqual(D(fill["fee"] if "fee" in fill else fill.get("fee_usd", "0")), 0)
        self.assertEqual(fill["liquidity"], "maker")
        self.assertTrue(self.book.reconcile().ok)
        # A taker fill keeps its label and its fee.
        taker = self.book.submit([self.intent("a1", event(), "buy", "5")])[0]
        self.assertEqual(taker.status, "filled")
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill", agent="a1")][-1]
        self.assertEqual(fill["liquidity"], "taker")

    def test_queued_buys_reserve_cash_fees_as_well_as_principal(self):
        self.book.reconcile()
        self.book.real_money = False  # isolate per-agent cash from the real floor's exposure caps
        self.seat("a1", usd="100")
        instruments = [event(ticker=f"KXTEST-26SEP20-T{number}") for number in range(4)]
        for instrument in instruments:
            self.broker.set_quote(instrument, "0.49", "0.50")
        intents = [self.intent("a1", instrument, "buy", "49") for instrument in instruments]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual([outcomes[i.id].status for i in intents], ["filled", "filled", "filled", "refused"])
        self.assertIn("free cash", outcomes[intents[-1].id].detail)
        self.assertGreater(self.book.account("a1").cash, 0)

    def test_one_batch_cannot_buy_both_legs_on_one_account(self):
        self.book.reconcile()
        self.seat("yes-buyer")
        self.seat("no-buyer")
        for instrument in (event("yes"), event("no")):
            self.broker.set_quote(instrument, "0.49", "0.50")
        intents = [self.intent("yes-buyer", event("yes"), "buy", "10"),
                   self.intent("no-buyer", event("no"), "buy", "10")]
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual(outcomes[intents[0].id].status, "filled")
        self.assertEqual(outcomes[intents[1].id].status, "refused")
        self.assertIn("one account cannot hold both", outcomes[intents[1].id].detail)

    def test_queued_event_buys_count_toward_the_whole_floors_cluster_cap(self):
        self.broker.cash = D("1000")
        self.book.reconcile()
        self.book.rules["max_event_cluster_floor_pct"] = "0.10"
        intents = []
        for number in range(3):
            agent = f"a{number}"
            self.seat(agent)
            instrument = event(ticker=f"KXBTCD-26SEP2017-T{80999 + number}")
            self.broker.set_quote(instrument, "0.49", "0.50")
            intents.append(self.intent(agent, instrument, "buy", "50"))
        outcomes = {out.intent_id: out for out in self.book.submit(intents)}
        self.assertEqual([outcomes[i.id].status for i in intents], ["filled", "filled", "refused"])
        self.assertIn("settle together", outcomes[intents[-1].id].detail)


class DailyLossRulesTest(BookCase):
    """The owner's revision of Sept 23, 2026 ~16:00 UTC (constitution `allocator.bunt_daily_loss` and
    `allocator.real_halt`): a real-money bunt is governed by the allocator's stay drawdown, not the
    book's per-desk daily loss, and the real book's halt is 8% of the venue's grant capital."""

    venue = "kalshi"
    family = "kalshi"
    real = True
    cash = "500"
    WEATHER = "KXHIGHNY-26SEP20-B80"  # another cluster: the crypto cluster's cap must not be what refuses

    def setUp(self):
        super().setUp()
        self.bands: dict[str, str] = {}
        self.basis: list = [D("517.75")]  # the Kalshi grant's capital
        # The event concentration caps read the grant's capital, as the House gives the real Kalshi book.
        self.book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=True, clock=self.clock,
                         band_of=lambda agent: self.bands.get(agent), halt_basis_usd=lambda: self.basis[0],
                         event_capital_budget=lambda: D("517.75"))
        self.book.reconcile()
        for ticker in ("KXBTCD-26SEP2017-T80999", "KXBTCD-26SEP2018-T80999", "KXBTCD-26SEP2019-T80999", self.WEATHER):
            self.broker.set_quote(event(ticker=ticker), "0.50", "0.52")

    def reasons(self, agent, ticker, quantity):
        instrument = event(ticker=ticker)
        return self.book.check(self.intent(agent, instrument, "buy", quantity), self.broker.quote(instrument), iso(self.clock))

    def lose(self, agent, ticker, quantity, mark):
        """Buy at the ask, then mark the holding down: a loss on the day, inside the same day."""
        out = self.book.submit([self.intent(agent, event(ticker=ticker), "buy", quantity)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.book.marks[event(ticker=ticker).key] = D(mark)

    def test_a_real_bunt_down_on_the_day_is_not_frozen_but_a_swing_still_is(self):
        self.seat("a1", usd="10", position="5", order="5")
        self.bands["a1"] = "bunt"
        self.lose("a1", "KXBTCD-26SEP2017-T80999", "5", "0.20")  # about 17% of the stake, on the day
        self.assertGreaterEqual(-self.book._day_pnl("a1", iso(self.clock)) / D(10), D("0.15"))
        self.assertFalse([r for r in self.reasons("a1", self.WEATHER, "1") if "daily loss" in r])
        self.assertEqual(self.book.risk_lines("a1")["desk_daily_loss_rule"], "stay_drawdown")
        self.bands["a1"] = "swing"
        self.assertTrue([r for r in self.reasons("a1", self.WEATHER, "1") if r.startswith("desk daily loss")])
        self.assertEqual(self.book.risk_lines("a1")["desk_daily_loss_pct"], 0.10)
        self.bands["a1"] = "bunt"
        with patch.dict(CONSTITUTION["allocator"], {"bunt_daily_loss": "book"}):
            self.assertTrue([r for r in self.reasons("a1", self.WEATHER, "1") if r.startswith("desk daily loss")])
        with patch.dict(CONSTITUTION["allocator"]):
            CONSTITUTION["allocator"].pop("bunt_daily_loss")  # the key absent: the book's rule, as before
            self.assertTrue([r for r in self.reasons("a1", self.WEATHER, "1") if r.startswith("desk daily loss")])
        book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=True, clock=self.clock,
                    event_capital_budget=lambda: D("517.75"))  # no House facts: the book's own rules
        book.limits["a1"] = Limits(D(5), D(5))
        book.marks.update(self.book.marks)
        book.day_open.update(self.book.day_open)
        instrument = event(ticker=self.WEATHER)
        self.assertTrue([r for r in book.check(self.intent("a1", instrument, "buy", "1"), self.broker.quote(instrument), iso(self.clock))
                         if r.startswith("desk daily loss")])

    def test_the_real_halt_is_a_share_of_the_venues_grant_capital_not_of_the_staked_sum(self):
        self.seat("a1", usd="200", position="60", order="60")
        self.seat("a2", usd="25", position="12.5", order="12.5")
        lost = ("KXBTCD-26SEP2017-T80999", "KXBTCD-26SEP2018-T80999", self.WEATHER)  # three markets: one is capped at 10% of the floor
        for ticker in lost:
            self.lose("a1", ticker, "35", "0.30")
        loss = -sum((self.book._day_pnl(a, iso(self.clock)) for a in ("a1", "a2")), D(0))
        self.assertTrue(D("0.08") * D(225) < loss < D("0.08") * D("517.75"), loss)  # over 8% of the stakes, under 8% of the grant
        self.assertFalse([r for r in self.reasons("a2", "KXBTCD-26SEP2019-T80999", "5") if "floor daily loss" in r])
        lines = self.book.risk_lines("a2")
        self.assertEqual((lines["halt_basis"], lines["halt_basis_usd"], lines["halt_pct"]), ("venue_grant_capital", 517.75, 0.08))
        self.basis[0] = D("1017.75")  # the combined envelope is never the basis of one venue's halt: the book takes what it is given
        self.assertFalse([r for r in self.reasons("a2", "KXBTCD-26SEP2019-T80999", "5") if "floor daily loss" in r])
        self.basis[0] = D("517.75")
        for ticker in lost:
            self.book.marks[event(ticker=ticker).key] = D("0.02")
        loss = -sum((self.book._day_pnl(a, iso(self.clock)) for a in ("a1", "a2")), D(0))
        self.assertGreater(loss, D("0.08") * D("517.75"))
        halted = [r for r in self.reasons("a2", "KXBTCD-26SEP2019-T80999", "5") if r.startswith("floor daily loss")]
        self.assertEqual(len(halted), 1, halted)
        self.assertIn("$517.75", halted[0])
        for ticker in lost:
            self.book.marks[event(ticker=ticker).key] = D("0.30")
        with patch.dict(CONSTITUTION["allocator"]["real_halt"], {"basis": "staked"}):  # the old basis, by the key
            self.assertTrue([r for r in self.reasons("a2", "KXBTCD-26SEP2019-T80999", "5") if r.startswith("floor daily loss")])
        self.basis[0] = None  # no grant names the venue: the old basis
        self.assertTrue([r for r in self.reasons("a2", "KXBTCD-26SEP2019-T80999", "5") if r.startswith("floor daily loss")])
        self.assertEqual(self.book.risk_lines("a2")["halt_basis"], "staked_accounts")


class DayOpenAcrossRestartTest(BookCase):
    """The #198 review (Sept 23, 2026, pre-existing): `Book.day_open` lived in memory only, so a House
    restart mid-day forgot every account's start-of-day equity, and both the per-desk daily-loss rule
    and the real book's halt started again from the restart's equity. The opening is persisted per
    book beside the ledger and restored at construction, with the day's stakes replayed from the
    ledger exactly as they adjusted it live."""

    venue = "kalshi"
    family = "kalshi"
    real = True
    cash = "500"
    LOST = ("KXBTCD-26SEP2017-T80999", "KXHIGHNY-26SEP20-B80")  # two clusters: no concentration cap refuses

    def setUp(self):
        super().setUp()
        self.basis: list = [D("200")]  # the halt: 8% of $200 = $16 of the day's loss
        self.book = self.restarted()
        for ticker in (*self.LOST, "KXBTCD-26SEP2019-T80999"):
            self.broker.set_quote(event(ticker=ticker), "0.50", "0.52")
        self.seat("a1", usd="200", position="100", order="75")

    def restarted(self, marks=True):
        """A House restart: a new Book folded from the same ledger, reconciled to the venue."""
        book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=True, clock=self.clock,
                    band_of=lambda agent: None, halt_basis_usd=lambda: self.basis[0], event_capital_budget=lambda: D("517.75"))
        book.reconcile()
        if getattr(self, "book", None) is not None:
            book.limits.update(self.book.limits)
            if marks:
                book.marks.update(self.book.marks)  # the marks come back with the first mark pass
        return book

    def lose(self, ticker, quantity, mark):
        out = self.book.submit([self.intent("a1", event(ticker=ticker), "buy", quantity)])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.book.marks[event(ticker=ticker).key] = D(mark)

    def halted(self):
        instrument = event(ticker="KXBTCD-26SEP2019-T80999")
        reasons = self.book.check(self.intent("a1", instrument, "buy", "1"), self.broker.quote(instrument), iso(self.clock))
        return [r for r in reasons if r.startswith("floor daily loss")]

    def day(self):
        return self.book._day_pnl("a1", iso(self.clock))

    def test_a_loss_before_a_restart_still_counts_after_it(self):
        self.lose(self.LOST[0], "40", "0.22")  # about -$12.70: 6% of the $200 basis
        before = self.day()
        self.assertTrue(D("-16") < before < D("-11"), before)
        self.assertEqual(self.halted(), [])
        self.clock.advance(600)
        self.book = self.restarted()
        self.assertEqual(self.day(), before)  # not zero: the restart does not forget the morning
        self.lose(self.LOST[1], "20", "0.22")  # about 3% more after the restart: 9% in all
        self.assertLess(self.day(), D("-16"))
        self.assertEqual(len(self.halted()), 1)  # refused at the 8% line, not given 8% more

    def test_a_new_utc_day_resets_the_opening(self):
        self.lose(self.LOST[0], "40", "0.22")
        self.assertLess(self.day(), D("-11"))
        self.clock.advance(86_400)
        self.book = self.restarted()
        self.assertEqual(self.day(), D(0))  # a new day opens at the equity it finds
        self.assertEqual(self.halted(), [])

    def test_a_stake_during_the_day_adjusts_the_opening_before_and_after_a_restart(self):
        self.lose(self.LOST[0], "40", "0.22")
        before = self.day()
        self.book.stake("a1", "50", note="capital lent is not the day's profit")
        self.assertEqual(self.day(), before)
        self.book.stake("a1", "-30", note="nor is capital taken back its loss")
        self.assertEqual(self.day(), before)
        self.clock.advance(600)
        self.book = self.restarted()
        self.assertEqual(self.day(), before)  # each stake adjusts the opening once: never twice, never forgotten
        self.book.stake("a1", "10", note="after the restart too")
        self.assertEqual(self.day(), before)
        self.book = self.restarted()
        self.assertEqual(self.day(), before)

    def test_an_unreadable_file_is_the_old_behaviour_not_a_crash(self):
        self.lose(self.LOST[0], "40", "0.22")
        path = self.book._day_open_path()
        self.assertTrue(path is not None and path.exists())
        path.write_text("{not json")
        self.book = self.restarted()
        self.assertEqual(self.day(), D(0))  # forgotten, as before this fix, and said nowhere worse


    # Review of #211 (Sept 23, 2026): marks live in memory only, and the House's startup reconcile quotes
    # only a position that differs from the venue, so until the first mark pass (up to 300 s later; the
    # tick's wakes come first) a holding was valued at cost against an opening taken at its mark.
    def test_a_holdings_loss_still_counts_before_the_first_mark_pass(self):
        self.lose(self.LOST[0], "60", "0.50")
        self.broker.set_quote(event(ticker=self.LOST[0]), "0.20", "0.22")
        self.book.mark()  # the day's loss is on the holding: 60 x $0.32 is past 8% of $200
        self.assertTrue(self.halted())
        self.book = self.restarted(marks=False)  # the first check after a restart, before the mark pass
        self.assertTrue(self.halted())  # was lifted: the holding read at its $0.52 cost

    def test_a_winner_unmarked_after_a_restart_is_not_a_false_halt(self):
        self.lose(self.LOST[0], "60", "0.50")
        self.clock.advance(86400)  # held overnight: the new day's opening is taken at the mark
        for ticker in (*self.LOST, "KXBTCD-26SEP2019-T80999"):
            self.broker.set_quote(event(ticker=ticker), "0.50", "0.52")
        self.broker.set_quote(event(ticker=self.LOST[0]), "0.90", "0.92")
        self.book.mark()
        self.assertEqual(self.day(), D(0))
        self.book = self.restarted(marks=False)
        self.assertEqual(self.day(), D(0))  # was -$22.80: a winner read at cost as the day's loss
        self.assertFalse(self.halted())


class PracticeDailyLossTest(BookCase):
    def test_a_practice_book_keeps_both_rules_whatever_the_house_says(self):
        self.book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=False, clock=self.clock,
                         band_of=lambda agent: "bunt", halt_basis_usd=lambda: D("100000"))
        self.seat("a1", usd="200", position="100", order="75")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertEqual(self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0].status, "filled")  # $40
        self.book.marks[BTC.key] = D("40000")  # down $20 on the day: 10% of the desk, and of the practice floor
        reasons = self.book.check(self.intent("a1", BTC, "buy", "0.0002"), self.broker.quote(BTC), iso(self.clock))
        self.assertTrue([r for r in reasons if r.startswith("desk daily loss")], reasons)
        self.assertFalse([r for r in reasons if "floor daily loss" in r], reasons)  # the halt never reached a practice book
        lines = self.book.risk_lines("a1")
        self.assertEqual((lines["desk_daily_loss_rule"], lines["desk_daily_loss_pct"], lines["halt_basis"]), ("book", 0.10, "staked_accounts"))


class CrossRecoveryTest(unittest.TestCase):
    def scenario(self, *, boundary=None, resume="restart", kalshi=False, same_agent=False, after=False, lost_ack=False):
        case = KalshiBookTest() if kalshi else BookCase()
        case.setUp()
        try:
            instrument = event() if kalshi else BTC
            case.broker.set_quote(instrument, "0.49" if kalshi else "80000", "0.50" if kalshi else "80010")
            case.book.reconcile()
            buyer, seller = ("trader", "trader") if same_agent else ("buyer", "seller")
            for agent in sorted({buyer, seller}):
                case.seat(agent)
            case.book.submit([case.intent(seller, instrument, "buy", "20" if kalshi else "0.0005")])
            quantity = case.book.account(seller).holdings[instrument.key].quantity
            intents = [case.intent(buyer, instrument, "buy", quantity), case.intent(seller, instrument, "sell", quantity)]
            submitted = len(case.broker.submitted)
            original = case.book._apply
            writes = 0

            def interrupted_apply(kind, agent, payload, at):
                nonlocal writes
                crossing = kind == "book.cross_plan" or (kind == "book.fill" and payload.get("source") in ("cross", "cross-house"))
                if crossing:
                    writes += 1
                    if writes == boundary and not after:
                        raise RuntimeError("process stopped before applying a committed cross row")
                result = original(kind, agent, payload, at)
                if crossing and writes == boundary and after:
                    raise RuntimeError("process stopped after applying a committed cross row")
                return result

            if lost_ack:
                append_many = case.ledger.append_many

                def committed_but_acknowledgement_lost(rows):
                    entries = append_many(rows)
                    if any(entry.kind == "book.cross_plan" for entry in entries):
                        raise RuntimeError("committed cross batch acknowledgement lost")
                    return entries

                with patch.object(case.ledger, "append_many", side_effect=committed_but_acknowledgement_lost):
                    with self.assertRaises(RuntimeError):
                        case.book.submit(intents)
            elif boundary is None:
                case.book.submit(intents)
            else:
                with patch.object(case.book, "_apply", side_effect=interrupted_apply):
                    with self.assertRaises(RuntimeError):
                        case.book.submit(intents)
            case.clock.advance(60)
            # Completion uses the old prices and costs from the plan, even with the venue down.
            with patch.object(case.broker, "quote", side_effect=AssertionError("recovery must not requote")), \
                 patch.object(case.broker, "submit", side_effect=AssertionError("recovery must not trade at the venue")), \
                 patch.object(case.broker, "get_order", side_effect=AssertionError("a cross has no venue order")):
                if resume == "restart":
                    case.book = case.new_book()
                elif resume == "submit":
                    self.assertEqual(case.book.submit([]), [])
                else:
                    self.assertEqual(case.book.poll(), 0)
                self.assertEqual(case.book.poll(), 0)
                again = case.new_book()
                self.assertEqual(again.poll(), 0)
            self.assertEqual(len(case.broker.submitted), submitted)
            self.assertFalse(case.book._cross_plans)
            self.assertFalse(case.book._cross_applied)
            self.assertTrue(case.book.reconcile().ok)
            self.assertTrue(again.reconcile().ok)
            plans = list(case.ledger.iter(kinds="book.cross_plan"))
            self.assertEqual(len(plans), 2)
            self.assertTrue(all(not entry.public for entry in plans))
            case.ledger.verify()
            return {
                "accounts": {
                    name: (account.cash, account.staked, account.realized, account.fees,
                           {key: (held.quantity, held.cost, held.opened_at, held.reason) for key, held in account.holdings.items()})
                    for name, account in case.book.accounts.items()
                },
                "fills": [(entry.id, entry.agent, entry.at, entry.payload) for entry in case.ledger.iter(kinds="book.fill")
                          if entry.payload.get("source") in ("cross", "cross-house")],
            }
        finally:
            case.tearDown()

    def test_restart_recovers_every_cross_boundary_with_exact_fees_and_timestamps(self):
        for kalshi in (False, True):
            expected = self.scenario(kalshi=kalshi)
            for after in (False, True):
                for boundary in range(1, 7):  # plan, buyer, buyer's House row, seller, seller's House row, completion
                    with self.subTest(kalshi=kalshi, boundary=boundary, after=after):
                        self.assertEqual(self.scenario(boundary=boundary, kalshi=kalshi, after=after), expected)

    def test_poll_or_new_intake_finishes_each_cross_without_restarting(self):
        expected = self.scenario()
        for resume in ("poll", "submit"):
            for after in (False, True):
                for boundary in range(1, 7):
                    with self.subTest(resume=resume, boundary=boundary, after=after):
                        self.assertEqual(self.scenario(boundary=boundary, resume=resume, after=after), expected)

    def test_multiple_sides_for_one_agent_preserve_sequential_cost_basis_after_restart(self):
        expected = self.scenario(same_agent=True)
        for after in (False, True):
            for boundary in range(1, 7):
                with self.subTest(boundary=boundary, after=after):
                    self.assertEqual(self.scenario(boundary=boundary, same_agent=True, after=after), expected)

    def test_a_committed_batch_with_a_lost_acknowledgement_recovers_without_a_venue_order(self):
        expected = self.scenario()
        for resume in ("restart", "poll", "submit"):
            with self.subTest(resume=resume):
                self.assertEqual(self.scenario(lost_ack=True, resume=resume), expected)

    def test_failure_inside_the_cross_transaction_leaves_no_partial_accounting(self):
        for boundary in range(1, 7):
            with self.subTest(boundary=boundary):
                case = BookCase()
                case.setUp()
                try:
                    case.seat("buyer")
                    case.seat("seller")
                    case.broker.set_quote(BTC, "80000", "80010")
                    case.book.reconcile()
                    case.book.submit([case.intent("seller", BTC, "buy", "0.0005")])
                    quantity = case.book.account("seller").holdings[BTC.key].quantity
                    original = case.ledger._append_one
                    writes = 0

                    def interrupted_transaction(kind, payload, **kwargs):
                        nonlocal writes
                        entry = original(kind, payload, **kwargs)
                        if kind == "book.cross_plan" or payload.get("source") in ("cross", "cross-house"):
                            writes += 1
                            if writes == boundary:
                                raise RuntimeError("failed before the transaction committed")
                        return entry

                    with patch.object(case.ledger, "_append_one", side_effect=interrupted_transaction):
                        with self.assertRaises(RuntimeError):
                            case.book.submit([case.intent("buyer", BTC, "buy", quantity), case.intent("seller", BTC, "sell", quantity)])
                    self.assertEqual(case.ledger.count(kinds="book.cross_plan"), 0)
                    self.assertFalse(any(row.payload.get("source") in ("cross", "cross-house") for row in case.ledger.iter(kinds="book.fill")))
                    again = case.new_book()
                    self.assertEqual(again.account("buyer").cash, D("200"))
                    self.assertEqual(again.account("buyer").holdings, {})
                    self.assertEqual(again.account("seller").holdings[BTC.key].quantity, quantity)
                    self.assertTrue(again.reconcile().ok)
                    self.assertEqual(len(case.broker.submitted), 1)
                    case.ledger.verify()
                finally:
                    case.tearDown()


if __name__ == "__main__":
    unittest.main()

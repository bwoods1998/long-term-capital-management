"""Listed options: long premium only, limit orders only, sold before they can be exercised.

Built on Sept 19, 2026 (a Saturday) for the market's open on the 21st, so nothing here has met a
real fill yet. What could not be measured is written to fail SAFE: an unexplained difference at
the venue freezes new entries, never exits.
"""

import unittest
from decimal import Decimal
from unittest import mock

from league.book import Book, Limits
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.ledger import now_iso
from league.tests.test_book import BookCase
from league.tests.test_house import HouseCase
from league.venues import instrument_for
from league import seeds

D = Decimal
NOW = "2026-09-21T15:00:00.000Z"  # a Monday, 11:00 in New York


def call(venue="alpaca-paper", occ="F261009C00013000"):
    return instrument_for(venue, {"occ": occ})


class Parsing(unittest.TestCase):
    def test_gateway_brokers_can_use_owner_configured_opra_without_silent_fallback(self):
        from league.venues import gateway_broker
        for venue in ('alpaca', 'alpaca-paper'):
            broker = gateway_broker(venue, gateway_url='https://gateway.test', token='test-token-' * 4, option_feed='opra')
            self.assertEqual(broker.option_feed, 'opra')
            self.assertEqual(broker.feed, 'iex')
        with self.assertRaises(ValueError):
            gateway_broker('alpaca', gateway_url='https://gateway.test', token='test-token-' * 4, option_feed='invented')

    def test_an_occ_symbol_is_an_option_of_a_hundred_shares(self):
        inst = call()
        self.assertEqual((inst.asset_class, inst.symbol, inst.expiry, inst.strike, inst.right, inst.multiplier), ("option", "F", "2026-10-09", D("13"), "call", D(100)))
        put = instrument_for("alpaca", {"occ": "spy260925p00700500"})
        self.assertEqual((put.symbol, put.strike, put.right), ("SPY", D("700.5"), "put"))
        self.assertEqual(inst.key, instrument_for("alpaca-paper", {"symbol": "F", "expiry": "2026-10-09", "strike": "13", "right": "call"}).key)

    def test_a_bad_occ_symbol_is_refused(self):
        for bad in ("F261009X00013000", "F26100C00013000", "TOOLONGROOT261009C00013000"):
            with self.assertRaises(ValueError):
                instrument_for("alpaca", {"occ": bad})


class BookRules(BookCase):
    def setUp(self):
        super().setUp()
        self.clock.now = 1790002800.0  # 2026-09-21T15:00:00Z
        self.broker.clock_iso = now_iso(self.clock)
        self.call = call()
        self.broker.set_quote(self.call, "0.40", "0.44")
        self.book.limits["a"] = Limits(D("100"), D("75"), asset_classes=("option",))
        self.book.stake("a", "200")

    def buy(self, instrument=None, **kw):
        kw.setdefault("order_type", "limit")
        kw.setdefault("limit_price", "0.44")
        return self.book.submit([self.intent("a", instrument or self.call, "buy", "1", **kw)])[0]

    def test_one_contract_costs_a_hundred_times_its_premium(self):
        outcome = self.buy()
        self.assertEqual(outcome.status, "filled", outcome.detail)
        account = self.book.account("a")
        self.assertEqual(account.cash, D("156"))
        self.assertEqual(self.book.equity("a"), D("196"))  # marked at the bid: 0.40 x 100
        self.assertTrue(self.book.reconcile().ok)

    def test_a_market_order_is_refused(self):
        outcome = self.buy(order_type="market", limit_price=None)
        self.assertEqual(outcome.status, "refused")
        self.assertIn("must be a limit order", outcome.detail)

    def test_a_contract_that_expires_today_cannot_be_entered_and_can_always_be_sold(self):
        today = call(occ="F260921C00013000")
        self.broker.set_quote(today, "0.10", "0.12")
        refused = self.buy(today, limit_price="0.12")
        self.assertIn("must expire after today", refused.detail)
        self.assertEqual(self.buy().status, "filled")
        self.clock.now += 18 * 86400  # its last day
        self.broker.clock_iso = now_iso(self.clock)
        sold = self.book.submit([self.intent("a", self.call, "sell", "1", order_type="limit", limit_price="0.40")])[0]
        self.assertEqual(sold.status, "filled", sold.detail)

    def test_two_contracts_over_the_order_cap_are_refused(self):
        outcome = self.book.submit([self.intent("a", self.call, "buy", "2", order_type="limit", limit_price="0.44")])[0]
        self.assertEqual(outcome.status, "refused")
        self.assertIn("$88.00", outcome.detail)

    def test_an_agent_outside_the_specialty_cannot_trade_options(self):
        self.book.limits["b"] = Limits(D("100"), D("75"))
        self.book.stake("b", "200")
        outcome = self.book.submit([self.intent("b", self.call, "buy", "1", order_type="limit", limit_price="0.44")])[0]
        self.assertEqual(outcome.status, "refused")

    def test_a_fifteen_minute_old_option_quote_is_accepted_and_a_thirty_minute_old_one_is_not(self):
        self.broker.clock_iso = "2026-09-21T14:44:00.000Z"  # the free feed's delay
        self.assertEqual(self.buy().status, "filled")
        other = call(occ="F261009C00014000")
        self.broker.set_quote(other, "0.20", "0.22")
        self.broker.clock_iso = "2026-09-21T14:29:00.000Z"
        self.assertIn("old", self.buy(other, limit_price="0.22").detail)

    # ---------------------------------------------------------------- expiry
    def test_an_expired_option_the_venue_has_cleared_is_written_off_at_zero(self):
        self.buy()
        self.clock.now += 19 * 86400  # the day after its expiry
        self.broker.clock_iso = now_iso(self.clock)
        self.assertEqual(self.book.expire_options(), 0)  # the venue still shows it: not yet
        self.broker.held.clear()
        self.assertEqual(self.book.expire_options(), 1)
        account = self.book.account("a")
        self.assertEqual((account.holdings, account.cash, account.realized), ({}, D("156"), D("-44")))
        self.assertEqual(self.book.expire_options(), 0)
        settle = [e.payload for e in self.ledger.iter(kinds="book.settle")][0]
        self.assertEqual((settle["result"], settle["payout"], D(settle["pnl"])), ("expired", "0", D("-44")))
        self.assertTrue(self.book.reconcile().ok)

    def test_an_option_is_not_written_off_before_its_expiry_has_passed(self):
        self.buy()
        self.broker.held.clear()
        self.assertEqual(self.book.expire_options(), 0)

    # ------------------------------------------------------------- venue fees
    def test_a_regulatory_fee_posted_at_the_end_of_the_day_is_booked_not_a_freeze(self):
        self.buy()
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.03")
        self.broker.fee_activities = lambda since=None: [{"id": "20260921::orf", "usd": D("0.03"), "date": "2026-09-21", "description": "ORF fee"}]
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        fee = [e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"]
        self.assertEqual([(e.agent, e.payload["cash_delta"], e.payload["detail"]) for e in fee], [("house", "-0.03", "2026-09-21 ORF fee")])
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(len([e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"]), 1)  # once

    def test_a_fee_larger_than_the_shortfall_explains_nothing_and_the_book_freezes(self):
        self.buy()
        self.assertTrue(self.book.reconcile().ok)  # the baseline is fixed here: what follows is a real shortfall
        self.broker.cash -= D("0.50")
        self.broker.fee_activities = lambda since=None: [{"id": "old", "usd": D("2.00"), "date": "2026-09-21", "description": "from before"}]
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertEqual([e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"], [])

    def test_a_shortfall_no_fee_explains_still_freezes(self):
        self.buy()
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.50")
        self.broker.fee_activities = lambda since=None: []
        self.assertFalse(self.book.reconcile().ok)

    def test_cash_the_venue_holds_behind_a_resting_option_bid_is_not_a_shortfall(self):
        self.assertEqual(self.buy().status, "filled")  # a book with money at stake never re-reads its baseline
        self.assertTrue(self.book.reconcile().ok)
        rest = self.buy(call(occ="F261009C00014000"), limit_price="0.41")
        self.assertEqual(rest.status, "resting", rest.detail)
        self.assertTrue(self.book.reconcile().ok)  # a venue that does not hold it back
        self.broker.cash -= D("41")  # and one that does, as Alpaca does for a resting crypto bid
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("5")  # but not a cent more than the bid
        self.assertFalse(self.book.reconcile().ok)


class InTheHouse(HouseCase):
    def options_agent(self, name="options-breakout", rung=1):
        agent = self.house.spawn(name, name, seeds.load(name), reason="test", specialty="alpaca-options")
        return agent

    def test_a_newcomer_to_a_specialty_without_replay_starts_on_paper_at_once(self):
        agent = self.options_agent()
        self.assertEqual((agent.specialty, self.house.evaluator.rung(agent.id)), ("alpaca-options", 1))
        self.assertEqual(self.house._replay_own(agent)["skipped"], "its code has had its replay; research may change it")
        self.assertEqual(list(self.house.ledger.iter(kinds="eval.trial")), [])  # nothing pretended to replay it

    def test_its_limits_are_options_only_and_the_micro_rung_allows_one_twenty_dollar_contract(self):
        agent = self.options_agent()
        paper = self.house._limits(1, agent)
        self.assertEqual((paper.asset_classes, paper.max_position_usd, paper.max_order_usd), (("option",), D("100"), D("75")))
        micro = self.house._limits(2, agent)
        self.assertEqual((micro.max_position_usd, micro.max_order_usd), (D("20"), D("20")))
        self.assertEqual(CONSTITUTION["rungs"]["2"]["option_max_position_usd"], "20")
        stock_agent = self.seated()
        self.assertNotIn("option", self.house._limits(1, stock_agent).asset_classes)
        self.assertEqual(self.house._limits(2, stock_agent).max_position_usd, D("10"))

    def test_the_chain_is_near_the_money_two_sided_affordable_and_after_today(self):
        asked = {}

        def option_chain(symbol, *, expiry_from, expiry_to):
            asked[symbol] = (expiry_from, expiry_to)
            row = lambda occ, strike, bid, ask: {"symbol": occ, "underlying": "F", "expiry": "2026-10-09", "strike": strike, "right": "call", "bid": bid, "ask": ask, "as_of": "x", "iv": 0.3, "delta": 0.5, "volume": 1.0}
            return [row("F261009C00013000", 13.0, 0.40, 0.44), row("F261009C00012000", 12.0, 1.10, 1.15), row("F261009C00020000", 20.0, 0.01, 0.02)]

        self.house.books["alpaca-paper"].broker.option_chain = option_chain
        rows = self.house._chain(["F"], 21, 0.75, {"F": {"bid": 12.9, "ask": 13.0}})
        self.assertEqual([r["occ"] for r in rows], ["F261009C00013000"])  # 1.15 is over one order; a $20 strike is half again the price
        self.assertEqual(rows[0]["underlying_price"], 12.95)
        first, last = asked["F"]
        today = now_iso(self.clock)[:10]
        self.assertGreater(first, today)
        self.assertGreater(last, first)

    def test_no_chain_where_the_venue_cannot_list_one(self):
        self.assertEqual(self.house._chain(["F"], 21, 0.75, {}), [])

    def test_a_long_option_is_sold_at_the_bid_on_its_last_afternoon(self):
        from league.book import Intent

        agent = self.options_agent()
        self.house.seat(agent)
        self.house._state["next_wake"][agent.id] = self.clock() + 10**9
        book = self.house.books["alpaca-paper"]
        expiring = call(occ="F260911C00013000")  # the fake clock's week: it expires on Friday Sept 11
        self.broker.set_quote(expiring, "0.40", "0.44")
        self.clock.now = 1789048800.0  # Thursday Sept 10, 14:00 UTC
        self.broker.clock_iso = now_iso(self.clock)
        bought = book.submit([Intent.new(agent=agent.id, instrument=expiring, side="buy", quantity="1", order_type="limit", limit_price="0.44", reason="t", created_at=now_iso(self.clock), nonce="b")])[0]
        self.assertEqual(bought.status, "filled", bought.detail)
        self.clock.now += 86400 + 3 * 3600  # Friday 17:00 UTC: 13:00 in New York
        self.broker.clock_iso = now_iso(self.clock)
        self.house._enforce_horizon()
        self.assertIn(expiring.key, book.account(agent.id).holdings)  # before 14:30: still its own
        self.clock.now += 2 * 3600  # 15:00 in New York
        self.broker.clock_iso = now_iso(self.clock)
        self.house._enforce_horizon()
        self.assertEqual(book.account(agent.id).holdings, {})
        sold = [e.payload for e in self.house.ledger.iter(kinds="agent.intent", agent=agent.id) if e.payload["side"] == "sell"]
        self.assertIn("expiry rule", sold[0]["reason"])
        self.assertTrue(book.reconcile().ok)

    def test_a_candidate_in_a_specialty_without_replay_is_smoke_run_not_replayed(self):
        agent = self.options_agent()
        self.house.seat(agent)
        good = self.house._candidate_replay(agent, seeds.load("options-pullback"))
        self.assertTrue(good["passed"], good)
        self.assertFalse(good["counted_as_trial"])
        self.assertIn("no replay", good["numbers"]["note"])
        broken = seeds.load("options-pullback").replace("def decide(ctx):", "def decide(ctx):\n    return 1 / 0\n\ndef _unused(ctx):")
        self.assertFalse(self.house._candidate_replay(agent, broken)["passed"])
        self.assertEqual(list(self.house.ledger.iter(kinds="eval.trial")), [])

    def test_a_smoke_run_on_a_shut_market_says_it_proved_nothing(self):
        """A weekend hands an options desk an empty view. Code that only ever answered "the session
        is closed" has not been tested -- not even on the path that matters -- and a pass there must
        not read like one."""
        agent = self.options_agent()
        self.house.seat(agent)
        self.house._offered = lambda a, ctx: 0
        shut = self.house._candidate_replay(agent, seeds.load("options-pullback"))
        self.assertTrue(shut["passed"])
        self.assertIs(shut["numbers"]["untested"], True)
        self.assertIn("its market is shut", shut["numbers"]["note"])
        self.house._offered = lambda a, ctx: 4
        open_now = self.house._candidate_replay(agent, seeds.load("options-pullback"))
        self.assertIs(open_now["numbers"]["untested"], False)


if __name__ == "__main__":
    unittest.main()


class FirstBaseline(BookCase):
    """A book that has never traded re-reads a baseline it cannot reconcile.

    Sept 19, 2026, on the league's first tick under the partners' names: a leftover bid from the
    league before it filled between the cash read and the position read of the new book's first
    baseline. The book froze $40 short with no agent having traded at all, and every Alpaca agent
    was blocked from entering anything.
    """

    def setUp(self):
        super().setUp()
        self.btc = instrument_for(self.venue, {"symbol": "BTC/USD"})
        self.broker.set_quote(self.btc, "79995", "80005")
        self.book.limits["a"] = Limits(D("100"), D("75"))
        self.book.stake("a", "200")

    def test_a_book_that_has_never_traded_reads_the_venue_again(self):
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("40")  # the moment moved between two reads
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertFalse(self.book.frozen)
        note = [e.payload for e in self.ledger.iter(kinds="book.baseline")][-1]
        self.assertIn("never traded", note["note"])
        self.assertIn("-40.0000", note["note"])
        self.assertEqual(D(note["cash"]), D("99960"))

    def test_once_it_has_traded_a_difference_freezes_it(self):
        self.assertTrue(self.book.reconcile().ok)
        outcome = self.book.submit([self.intent("a", self.btc, "buy", "0.0001")])[0]
        self.assertEqual(outcome.status, "filled", outcome.detail)
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("40")
        self.assertFalse(self.book.reconcile().ok)
        self.assertEqual(len([e for e in self.ledger.iter(kinds="book.baseline") if "never traded" in e.payload["note"]]), 0)

    def test_an_order_resting_at_the_venue_has_moved_no_money(self):
        self.assertTrue(self.book.reconcile().ok)
        rest = self.book.submit([self.intent("a", self.btc, "buy", "0.0001", order_type="limit", limit_price="76000")])[0]
        self.assertEqual(rest.status, "resting", rest.detail)
        self.broker.cash -= D("40")
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)  # nothing of the league's is hidden by reading again
        self.assertIn("never traded", [e.payload for e in self.ledger.iter(kinds="book.baseline")][-1]["note"])

    def test_the_baseline_waits_for_a_foreign_order_to_stop_working(self):
        slept = []
        book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=False, clock=self.clock, sleep=slept.append)
        working = [object()]

        def open_orders():
            return [type("O", (), {"id": "foreign", "broker_order_id": "foreign"})()] if working else []

        self.broker.open_orders = open_orders
        self.broker.cancel = lambda _id: working.clear()
        book.open_baseline()
        self.assertEqual(slept, [])  # it stopped working at once
        self.assertIsNotNone(book.baseline_cash)

    def test_a_practice_book_takes_the_venues_word_rather_than_freeze_for_ever(self):
        """Sept 20, 2026: an order to the paper account filled, its poll failed on a transport
        error, and the book never learned. It held $40 of LTC the book did not know about and
        froze -- which stops EVERY agent on that venue, and it had been frozen ninety minutes
        before anybody looked. A lost order must cost the desk that lost it, not the venue."""
        from league.book import ADOPT_AFTER

        self.assertTrue(self.book.reconcile().ok)
        self.book.submit([self.intent("a", self.btc, "buy", "0.0001")])
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("40")  # a fill the book never saw
        for _ in range(ADOPT_AFTER - 1):
            self.assertFalse(self.book.reconcile().ok)  # it is given time to settle itself first
        self.assertTrue(self.book.reconcile().ok)
        self.assertFalse(self.book.frozen)
        note = [e.payload for e in self.ledger.iter(kinds="book.baseline")][-1]
        self.assertIn("adopted the venue", note["note"])
        self.assertIn("cash differs by -40.0000", note["note"])
        self.assertEqual(self.book.account("a").realized, D("0"))  # no agent's record is flattered by it

    def test_a_real_money_book_freezes_and_stays_frozen(self):
        from league.book import ADOPT_AFTER

        self.book.real_money = True
        self.assertTrue(self.book.reconcile().ok)
        self.book.submit([self.intent("a", self.btc, "buy", "0.0001")])
        self.broker.cash -= D("40")
        for _ in range(ADOPT_AFTER + 2):
            self.assertFalse(self.book.reconcile().ok)
        self.assertEqual([e for e in self.ledger.iter(kinds="book.baseline") if "adopted" in e.payload["note"]], [])

    def test_a_position_the_ledger_never_learned_of_still_reaches_the_adoption(self):
        """`_traded_yet` is false when no account holds anything, so the counter never moved and
        the never-traded re-read corrects CASH only -- leaving the position diff to freeze the book
        for ever, in exactly the state the adoption exists to clear. Found by the stall audit."""
        from league.book import ADOPT_AFTER

        self.assertTrue(self.book.reconcile().ok)
        self.broker.held[self.btc.key] = (self.btc, D("0.5"))   # the venue holds what no agent ever bought
        for _ in range(ADOPT_AFTER - 1):
            self.assertFalse(self.book.reconcile().ok)
        healed = self.book.reconcile()
        self.assertTrue(healed.ok, healed.detail)
        note = [e.payload for e in self.ledger.iter(kinds="book.baseline")][-1]
        self.assertIn("adopted the venue", note["note"])

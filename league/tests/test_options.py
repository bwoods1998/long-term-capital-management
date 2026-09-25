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
from league.tests.fakes import old_ladder
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

    def test_the_chain_rows_symbol_names_the_contract(self):
        """The chain gives the OCC code as `symbol`; passed back that way it is the option, not a ticker."""
        inst = instrument_for("alpaca-paper", {"symbol": "AAL261002P00013500", "side": "buy"})
        self.assertEqual((inst.asset_class, inst.symbol, inst.strike, inst.right), ("option", "AAL", D("13.5"), "put"))
        self.assertEqual(instrument_for("alpaca", {"symbol": "AAL"}).asset_class, "equity")

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
        # A dollar and more: under `PRACTICE_DUST_USD` a practice book books the cents as dust (Sept 24, 2026).
        self.buy()
        self.assertTrue(self.book.reconcile().ok)  # the baseline is fixed here: what follows is a real shortfall
        self.broker.cash -= D("1.50")
        self.broker.fee_activities = lambda since=None: [{"id": "old", "usd": D("2.00"), "date": "2026-09-21", "description": "from before"}]
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertEqual([e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"], [])

    def test_a_shortfall_no_fee_explains_still_freezes(self):
        self.buy()
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("1.50")  # a dollar and more (`PRACTICE_DUST_USD`)
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


class PracticeOptionFees(BookCase):
    """A practice option fill pays the OCC clearing fee Alpaca's paper account takes at the fill
    (`Fees.option_clearing`, Sept 24, 2026): $0.03 a contract rounded up to the cent a fill, which the
    venue lists only the next morning. Until then every option fill left the book three cents over the
    venue (14:39:07Z: "cash differs by -0.0322", krasker-14's AAL buy), and the next morning's row was
    booked again against whatever shortfall came next."""

    def new_book(self):
        return Book(self.venue, self.broker, self.ledger, fees=Fees(self.family, option_clearing=True), real_money=self.real,
                    clock=self.clock)

    def setUp(self):
        super().setUp()
        self.broker.fees = Fees("alpaca", option_clearing=True)  # the paper venue takes it at the fill
        self.clock.now = 1790002800.0  # 2026-09-21T15:00:00Z
        self.broker.clock_iso = now_iso(self.clock)
        self.call = call()
        self.broker.set_quote(self.call, "0.40", "0.44")
        self.book.limits["a"] = Limits(D("100"), D("75"), asset_classes=("option",))
        self.book.stake("a", "200")

    def trade(self, side="buy", price="0.44"):
        return self.book.submit([self.intent("a", self.call, side, "1", order_type="limit", limit_price=price)])[0]

    def venue_fee_rows(self):
        return [e.payload for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"]

    def test_the_model_charges_three_cents_a_contract_rounded_up_a_fill_and_only_when_asked(self):
        fees = Fees("alpaca", option_clearing=True)
        self.assertEqual([fees.charge(self.call, side, D(n), D("0.44")).usd for side, n in (("buy", 1), ("sell", 1), ("sell", 2), ("buy", 3))],
                         [D("0.03"), D("0.03"), D("0.05"), D("0.08")])
        self.assertEqual(Fees("alpaca").charge(self.call, "buy", D(1), D("0.44")).usd, D(0))  # a real book: not measured yet
        spy = instrument_for("alpaca-paper", {"symbol": "SPY"})
        self.assertEqual(fees.charge(spy, "sell", D(1), D("500")).usd, D(0))  # equities unchanged

    def test_the_fill_pays_the_fee_and_the_book_reconciles_to_the_cent(self):
        self.assertEqual(self.trade().status, "filled")
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue"][-1]
        self.assertEqual((D(fill["fee_usd"]), D(fill["cash_delta"])), (D("0.03"), D("-44.03")))
        self.assertEqual(self.book.account("a").cash, D("155.97"))
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.dust_booked, D(0))
        self.assertEqual(self.trade("sell", "0.40").status, "filled")
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, D(0)))
        self.assertEqual(self.book.account("a").realized, D("-4.06"))  # the premium's $4 and both fills' fees

    def test_the_next_mornings_clearing_row_is_not_booked_again_and_the_regulators_are(self):
        self.assertEqual(self.trade().status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.02")  # the overnight batch takes the day's ORF
        self.broker.fee_activities = lambda since=None: [
            {"id": "20260921::occ", "usd": D("0.03"), "date": "2026-09-21", "description": "OCC Clearing Fee"},
            {"id": "20260921::orf", "usd": D("0.02"), "date": "2026-09-21", "description": "ORF fee for proceed of 1 contracts"}]
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.dust_booked, D(0))
        self.assertEqual([(row["detail"], row["cash_delta"]) for row in self.venue_fee_rows()],
                         [("2026-09-21 ORF fee for proceed of 1 contracts", "-0.02")])

    def test_a_shortfall_beside_a_fill_in_flight_books_no_fee(self):
        """Sept 24, 2026, 11:29:48Z: an in-flight BTC buy read "cash differs by -24.1299; positions
        differ: crypto:BTCUSD:alpaca-paper 0.000299081", and $0.87 of the day before's fee rows were
        booked against it; the fill landed seven seconds later and the book froze on +0.8700 for ten
        minutes, until it adopted the venue."""
        self.assertEqual(self.trade().status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.broker.fee_activities = lambda since=None: [
            {"id": "20260923::orf", "usd": D("0.38"), "date": "2026-09-23", "description": "ORF fee for proceed of 25 contracts"},
            {"id": "20260923::taf", "usd": D("0.04"), "date": "2026-09-23", "description": "OPT TAF fee for proceed of 11 contracts"}]
        btc = instrument_for("alpaca-paper", {"symbol": "BTC/USD"})
        self.broker.cash -= D("24.13")  # the venue shows a fill the book has not polled yet
        self.broker.held[btc.key] = (btc, D("0.000299081"))
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertIn("positions differ", result.detail)
        self.assertEqual(self.venue_fee_rows(), [])  # the price of units is not a fee
        self.broker.cash += D("24.13")
        self.broker.held.pop(btc.key)
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual((result.dust_booked, self.venue_fee_rows()), (D(0), []))


@old_ladder()
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
        self.assertEqual((micro.max_position_usd, micro.max_order_usd), (D("40"), D("40")))
        self.assertEqual(CONSTITUTION["rungs"]["2"]["option_max_position_usd"], "40")
        stock_agent = self.seated()
        self.assertNotIn("option", self.house._limits(1, stock_agent).asset_classes)
        self.assertEqual(self.house._limits(2, stock_agent).max_position_usd, D("30"))

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


class OptionsTapes(HouseCase):
    """The replay's options tape (`House.tape_for`) for a structure agent (Sept 25, 2026): its own cache key,
    and the feeds it declares."""

    NEEDS = {"venue": "alpaca", "horizon": "day", "asset_class": "option", "symbols": ["SPY"], "max_days_to_expiry": 7}

    def setUp(self):
        super().setUp()
        built = self.built = []

        class History:
            def tape(self, needs, start, end, **kw):
                built.append(dict(needs))
                return {"steps": [], "structures": bool(needs.get("structures"))}

            def feature_series(self, symbols):
                return {}

        self.house.options_history = History()

    def test_a_structure_agent_and_a_single_contract_agent_never_share_a_tape(self):
        single, _ = self.house.tape_for(self.NEEDS)
        structural, tape = self.house.tape_for({**self.NEEDS, "structures": True})
        zero, _ = self.house.tape_for({**self.NEEDS, "structures": True, "max_days_to_expiry": 0})
        unsaid, _ = self.house.tape_for({k: v for k, v in {**self.NEEDS, "structures": True}.items() if k != "max_days_to_expiry"})
        featured, _ = self.house.tape_for({**self.NEEDS, "structures": True, "options_features": True})
        self.assertEqual(len({single, structural, zero, unsaid, featured}), 5)
        self.assertEqual(len(self.built), 5)
        self.assertTrue(tape["structures"])
        self.assertEqual(self.house.tape_for({**self.NEEDS, "structures": True})[0], structural)  # and a tape is still shared
        self.assertEqual(len(self.built), 5)

    def test_a_structure_agents_tape_carries_its_feeds_and_a_single_contract_agents_is_refused_them(self):
        class Feeds:
            def coverage(self, wanted, start, end):
                return {"earnings": {"INTC": {"first_ok": "2026-09-01T00:00:00Z"}}}

            def series(self, wanted, start, end, step):
                return {"earnings": {"INTC": [{"t": "2026-09-09T20:05:00Z", "item": "2.02"}]}}

            def close(self):
                pass

        self.house.feeds = Feeds()
        self.house._feeds_wanted = lambda needs: {"earnings": ["INTC"]} if needs.get("feeds") else {}
        self.house._feeds_shortfall = lambda needs, wanted, coverage: ""
        needs = {**self.NEEDS, "structures": True, "feeds": {"earnings": ["INTC"]}}
        _, tape = self.house.tape_for(needs)
        self.assertEqual(tape["feeds"]["earnings"]["INTC"][0]["item"], "2.02")
        self.house._require_feeds(needs, {"earnings": ["INTC"]}, tape["feeds_coverage"])  # no refusal
        _, plain = self.house.tape_for({**self.NEEDS, "feeds": {"earnings": ["INTC"]}})
        self.assertNotIn("feeds", plain)
        with self.assertRaises(ValueError):
            self.house._require_feeds({**self.NEEDS, "feeds": {"earnings": ["INTC"]}}, {"earnings": ["INTC"]}, {})


# ------------------------------------------------------------------ structures (Sept 25, 2026)
#: A structure agent: the options desk, `"structures": True` in its NEEDS. It sends what a test put in its memory.
STRUCTURE_AGENT = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "asset_class": "option", "structures": True, "symbols": ["SPY"],
         "max_days_to_expiry": 7, "wake_minutes": 15, "style": "test-structures"}
PARAMS = {"structure": "iron_condor", "width": 1.0}

def decide(ctx):
    return {"intents": list((ctx.get("memory") or {}).get("send") or []), "memory": ctx.get("memory") or {}}
'''
THURSDAY_11_NY = 1789052400.0  # Thursday Sept 10, 2026, 15:00 UTC: 11:00 in New York, in the session
SPOT = 585.5


def occ(expiry, right, strike):
    return f"SPY{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{'C' if right == 'call' else 'P'}{int(strike * 1000):08d}"


def condor_row(expiry="2026-09-11", *, action="open", limit=0.38, quantity=1, **extra):
    """A $1-winged SPY iron condor (580/581 puts, 590/591 calls): at a 0.38 credit it is held at 0.62, $62 at risk."""
    legs = [{"occ": occ(expiry, "put", 580), "role": "long"}, {"occ": occ(expiry, "put", 581), "role": "short"},
            {"occ": occ(expiry, "call", 590), "role": "short"}, {"occ": occ(expiry, "call", 591), "role": "long"}]
    return {"structure": "iron_condor", "action": action, "quantity": quantity, "limit_price": limit, "legs": legs, "reason": "a test condor", **extra}


def fake_chain(asked=None, expiries=("2026-09-10", "2026-09-11", "2026-09-14")):
    """An SPY chain around 585.5, strikes 560-610 a dollar apart: the at-the-money contracts cost over $5 (far
    over the single contract's $0.75 line), the wings a few cents."""
    def option_chain(symbol, *, expiry_from, expiry_to):
        if asked is not None:
            asked.append((symbol, expiry_from, expiry_to))
        rows = []
        for expiry in expiries:
            if not expiry_from <= expiry <= expiry_to:
                continue
            for strike in range(560, 611):
                for right in ("call", "put"):
                    inside = max(0.0, SPOT - strike) if right == "call" else max(0.0, strike - SPOT)
                    price = round(max(0.05, inside + 3.0 - 0.25 * abs(strike - SPOT)), 2)
                    rows.append({"symbol": occ(expiry, right, strike), "underlying": "SPY", "expiry": expiry, "strike": float(strike),
                                 "right": right, "bid": round(price - 0.02, 2), "ask": round(price + 0.02, 2), "as_of": "x",
                                 "iv": 0.2, "delta": (0.5 if right == "call" else -0.5), "volume": 100.0})
        return rows
    return option_chain


class StructureHouseCase(HouseCase):
    """A House with the options shadow book beside the practice book (a fake venue that fills a limit that
    crosses its quote), in the session, SPY at 585.5. No tests of its own: `StructuresInTheHouse` and
    `league/tests/test_options_desk.py` build on it."""

    def new_house(self, **kw):
        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from league.tests.fakes import FakeBroker
        from pathlib import Path

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        kw.setdefault("game", game)
        self.shadow = FakeBroker("options-shadow")
        house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker, "alpaca": FakeBroker("alpaca", cash="500"),
                                                    "options-shadow": self.shadow},
            sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock,
            settings=Settings(mark_every_seconds=0, research=False), **kw,
        )
        house.structure_book_name = "options-shadow"  # what league/config.json names by default
        return house

    def setUp(self):
        super().setUp()
        self.clock.now = THURSDAY_11_NY
        self.shadow.clock_iso = self.broker.clock_iso = now_iso(self.clock)
        self.data.price = SPOT

    def structure_agent(self, name="krasker"):
        return self.house.spawn(name, "options-structures-test", STRUCTURE_AGENT, reason="test", specialty="alpaca-options")

    def refusals(self, agent):
        return [r for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id) for r in e.payload["reasons"]]

    def at(self, epoch):
        self.clock.now = epoch
        self.shadow.clock_iso = self.broker.clock_iso = now_iso(self.clock)


class StructuresInTheHouse(StructureHouseCase):
    """The House's structure hooks (S2 of the options-desk run, Sept 25, 2026): a structure agent's book,
    its intents, its chain and `ctx["structures"]`, its positions, and the expiry-day close."""

    # -- who, and which book
    def test_a_structure_agent_practises_on_the_structure_book_and_a_single_leg_agent_is_unchanged(self):
        agent = self.structure_agent()
        single = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.assertTrue(self.house.is_structure_agent(agent))
        self.assertFalse(self.house.is_structure_agent(single))
        self.assertIs(self.house.book_of(agent), self.house.books["options-shadow"])
        self.assertIs(self.house.book_of(single), self.house.books["alpaca-paper"])
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)  # the options desk's practice starts at once

    def test_the_book_is_read_from_the_config_and_defaults_to_the_shadow_book(self):
        from league import house as house_module

        self.house.structure_book_name = None
        with mock.patch.object(house_module.Path, "read_text", side_effect=OSError("unreadable")):
            self.assertEqual(self.house._structure_book_name(), "options-shadow")
        self.house.structure_book_name = None
        with mock.patch.object(house_module.json, "loads", return_value={"options_structures": {"book": "alpaca-paper"}}):
            self.assertEqual(self.house._structure_book_name(), "alpaca-paper")

    # -- intents
    def test_a_structure_intent_is_one_held_instrument_limit_on_the_structure_book(self):
        from league import structures

        agent = self.structure_agent()
        book = self.house.book_of(agent)
        intents, dropped = self.house._intents(agent, book, [condor_row(), condor_row(action="close", limit=0.10)])
        self.assertEqual(dropped, [])
        opened, closed = intents
        spec = structures.parse("options-shadow", condor_row()).spec
        self.assertEqual(opened.instrument, structures.instrument(spec, "options-shadow"))
        self.assertTrue(structures.is_structure(opened.instrument))
        # A 0.38 credit on $1 wings is held at 0.62 (its maximum loss); buying it back for at most 0.10 sells it at 0.90 or more.
        self.assertEqual((opened.side, opened.order_type, opened.limit_price, opened.quantity), ("buy", "limit", D("0.62"), D("1")))
        self.assertEqual((closed.side, closed.limit_price), ("sell", D("0.90")))
        self.assertEqual(opened.reason, "a test condor")

    def test_a_net_price_is_never_snapped_to_a_single_contracts_grid(self):
        agent = self.structure_agent()
        book = self.house.book_of(agent)
        wide = {"structure": "debit_vertical", "action": "open", "quantity": 1, "limit_price": 3.37, "reason": "a $5 call vertical",
                "legs": [{"occ": occ("2026-09-11", "call", 580), "role": "long"}, {"occ": occ("2026-09-11", "call", 585), "role": "short"}]}
        with mock.patch("league.house.price_increment", return_value=D("0.05")):  # were a nickel grid ever known for options
            intents, dropped = self.house._intents(agent, book, [wide])
            self.assertIsNone(self.house._price_increment(book, intents[0].instrument, D("3.37")))
        self.assertEqual((dropped, intents[0].limit_price), ([], D("3.37")))

    def test_the_verticals_alias_is_read(self):
        agent = self.structure_agent()
        row = {"spread": "debit_vertical", "side": "buy", "quantity": 1, "limit_price": 0.45, "reason": "alias",
               "legs": [{"occ": occ("2026-09-11", "call", 585), "role": "long"}, {"occ": occ("2026-09-11", "call", 586), "role": "short"}]}
        intents, dropped = self.house._intents(agent, self.house.book_of(agent), [row])
        self.assertEqual((dropped, intents[0].side, intents[0].limit_price), ([], "buy", D("0.45")))

    def test_a_structure_that_is_not_defined_risk_is_dropped_with_the_reason(self):
        agent = self.structure_agent()
        naked = {"structure": "credit_vertical", "action": "open", "quantity": 1, "limit_price": 0.40, "reason": "naked",
                 "legs": [{"occ": occ("2026-09-11", "put", 581), "role": "short"}, {"occ": occ("2026-09-11", "put", 581), "role": "short"}]}
        intents, dropped = self.house._intents(agent, self.house.book_of(agent), [naked, condor_row(limit=1.00)])
        self.assertEqual(intents, [])
        self.assertEqual(len(dropped), 2)
        self.assertIn("not a defined-risk order", dropped[1])  # a credit at its collateral could never lose

    def test_a_structure_intent_from_an_agent_that_is_not_a_structure_agent_is_refused(self):
        single = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        intents, dropped = self.house._intents(single, self.house.book_of(single), [condor_row()])
        self.assertEqual((intents, dropped), ([], []))
        self.assertIn("only from a structure agent", self.refusals(single)[0])

    def test_a_structure_agents_single_leg_intent_is_refused(self):
        agent = self.structure_agent()
        row = {"occ": occ("2026-09-11", "call", 590), "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.40, "reason": "one leg"}
        intents, dropped = self.house._intents(agent, self.house.book_of(agent), [row])
        self.assertEqual((intents, dropped), ([], []))
        self.assertIn("holds structures only", self.refusals(agent)[0])

    def test_no_open_from_1430_new_york_on_the_earliest_expiry_day_but_a_close_goes(self):
        agent = self.structure_agent()
        book = self.house.book_of(agent)
        self.at(THURSDAY_11_NY + 86400 + 2 * 3600)  # Friday 13:00 New York: the Friday condor may still open
        intents, _ = self.house._intents(agent, book, [condor_row()])
        self.assertEqual(len(intents), 1)
        self.at(THURSDAY_11_NY + 86400 + 3.75 * 3600)  # Friday 14:45 New York
        intents, _ = self.house._intents(agent, book, [condor_row(), condor_row(action="close", limit=0.10),
                                                       condor_row(expiry="2026-09-14")])
        self.assertEqual([(i.side, i.instrument.expiry) for i in intents], [("sell", "2026-09-11"), ("buy", "2026-09-14")])
        self.assertIn("from 14:30 New York", self.refusals(agent)[0])

    def test_an_early_close_moves_the_entry_cut_and_the_house_close_before_the_bell(self):
        """The day after Thanksgiving closes at 13:00 New York: a 15:30 close would come after the bell."""
        self.assertEqual(self.house._structure_hours("2026-09-25"), (14.5, 15.5))
        self.assertEqual(self.house._structure_hours("2026-11-27"), (11.5, 12.5))
        agent = self.structure_agent()
        self.at(1795797900.0)  # Friday Nov 27, 2026, 16:45 UTC: 11:45 in New York, in its short session
        intents, _ = self.house._intents(agent, self.house.book_of(agent), [condor_row(expiry="2026-11-27")])
        self.assertEqual(intents, [])
        self.assertIn("from 11:30 New York", self.refusals(agent)[0])

    def test_no_open_outside_the_session(self):
        agent = self.structure_agent()
        self.at(THURSDAY_11_NY - 13 * 3600)  # Thursday 02:00 UTC
        intents, _ = self.house._intents(agent, self.house.book_of(agent), [condor_row()])
        self.assertEqual(intents, [])
        self.assertIn("outside the regular session", self.refusals(agent)[0])

    def test_structures_on_real_money_wait_for_the_owners_switch(self):
        from types import SimpleNamespace

        agent = self.structure_agent()
        real = SimpleNamespace(name="alpaca", real_money=True, broker=SimpleNamespace(venue="alpaca"))
        intents, dropped = self.house._intents(agent, real, [condor_row(), condor_row(action="close", limit=0.10)])
        self.assertEqual((intents, dropped), ([], []))
        self.assertTrue(all("owner's switch (O1)" in r for r in self.refusals(agent)))

    def test_a_missing_structure_book_refuses_and_never_sends_to_alpaca_paper(self):
        agent = self.structure_agent()
        self.house.structure_book_name = "no-such-book"
        book = self.house.book_of(agent)
        self.assertIs(book, self.house.books["alpaca-paper"])  # seated on the desk's practice book...
        intents, _ = self.house._intents(agent, book, [condor_row()])
        self.assertEqual(intents, [])  # ...where nothing it sends goes
        self.assertIn("no-such-book book, which is not open on this House", self.refusals(agent)[0])

    def test_a_paused_agents_open_is_held_and_its_close_goes(self):
        agent = self.structure_agent()
        with mock.patch.object(self.house.registry, "entries_paused", return_value={"since": now_iso(self.clock), "session": "x"}):
            intents, dropped = self.house._intents(agent, self.house.book_of(agent), [condor_row(), condor_row(action="close", limit=0.10)])
        self.assertEqual(([i.side for i in intents], dropped, self.refusals(agent)), (["sell"], [], []))

    # -- the chain and ctx["structures"]
    def test_the_chain_of_a_structure_agent_is_unaffordable_by_one_contract_and_starts_today(self):
        asked = []
        self.broker.option_chain = fake_chain(asked)
        rows = self.house._chain(["SPY"], 7, None, {"SPY": {"bid": SPOT - 0.01, "ask": SPOT + 0.01}}, structures=True)
        self.assertEqual(sorted({r["expiry"] for r in rows}), ["2026-09-10", "2026-09-11", "2026-09-14"])  # 0 DTE before 14:30 New York
        self.assertLessEqual(len(rows), 80)
        self.assertTrue(any(r["ask"] > 0.75 for r in rows))  # over the single contract's line
        # ONE ranged request (306 rows: under the split line), Thursday to the next Thursday.
        self.assertEqual(asked, [("SPY", "2026-09-10", "2026-09-17")])
        self.house._chain(["SPY"], 2, None, {"SPY": {"bid": SPOT, "ask": SPOT}}, structures=True)
        self.assertEqual(len(asked), 1)  # shared, by an agent asking fewer days too: read again only after two minutes
        self.at(THURSDAY_11_NY + 3.75 * 3600)  # 14:45 New York: today's expiry is no longer shown
        rows = self.house._chain(["SPY"], 7, None, {"SPY": {"bid": SPOT, "ask": SPOT}}, structures=True)
        self.assertNotIn("2026-09-10", {r["expiry"] for r in rows})

    def test_a_chain_near_the_adapters_page_is_read_one_trading_day_at_a_time_and_stays_so_for_the_day(self):
        asked = []
        days = ("2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17")
        self.broker.option_chain = fake_chain(asked, expiries=days)  # 612 rows over the window: a cut page
        rows = self.house._chain(["SPY"], 7, None, {"SPY": {"bid": SPOT, "ask": SPOT}}, structures=True)
        self.assertEqual(asked[0], ("SPY", "2026-09-10", "2026-09-17"))
        self.assertEqual([a[1] for a in asked[1:]], list(days))  # then one an expiry, trading days only (no weekend)
        self.assertTrue(all(a[1] == a[2] for a in asked[1:]))
        self.assertEqual(sorted({r["expiry"] for r in rows}), sorted(days))
        self.at(self.clock() + 180)  # past the two minutes: straight to the expiries, no ranged request again today
        self.house._chain(["SPY"], 7, None, {"SPY": {"bid": SPOT, "ask": SPOT}}, structures=True)
        self.assertEqual([a[1] for a in asked[7:]], list(days))
        self.assertEqual(self.house._trading_days("2026-11-25", "2026-11-30"), ["2026-11-25", "2026-11-27", "2026-11-30"])  # no Thanksgiving

    def test_a_structure_marked_at_zero_shows_its_loss_not_its_cost(self):
        """The adversarial review (Sept 25, 2026): `mark or average_cost` showed a worthless condor at its cost."""
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        book.marks[inst.key] = D("0")  # what the book marks a structure whose bid comes to nothing (s1/shadow 0bba5c1)
        row = self.house.snapshot(agent, book)["positions"][0]
        self.assertEqual((row["mark"], row["natural_mark"]), (0.0, 1.0))  # the whole wing to buy it back
        self.assertAlmostEqual(row["pnl_usd"], round(-row["average_cost"] * 100, 2))

    def test_a_zero_dte_strategy_is_shown_today_only(self):
        """Regression: `max_days_to_expiry: 0` read as "unsaid" (a falsy 0) showed a 0-DTE strategy a week."""
        self.broker.option_chain = fake_chain()
        agent = self.house.spawn("krasker", "options-0dte-test", STRUCTURE_AGENT.replace('"max_days_to_expiry": 7', '"max_days_to_expiry": 0'),
                                 reason="test", specialty="alpaca-options")
        self.house.seat(agent)
        ctx = self.house.snapshot(agent, self.house.book_of(agent))
        self.assertEqual({row["expiry"] for row in ctx["chain"]}, {"2026-09-10"})
        self.assertTrue(ctx["structures"])
        self.assertEqual({row["days_to_expiry"] for row in ctx["structures"]}, {0})

    def test_the_wake_shows_the_chain_and_structures_within_the_caps(self):
        self.broker.option_chain = fake_chain()
        agent = self.structure_agent()
        book = self.house.book_of(agent)
        self.house.seat(agent)
        ctx = self.house.snapshot(agent, book)
        self.assertTrue(ctx["chain"])
        cap = min(ctx["limits"]["max_order_usd"], ctx["limits"]["max_position_usd"])
        self.assertTrue(ctx["structures"])
        self.assertTrue(all(0 < row["max_loss_usd"] <= cap for row in ctx["structures"]))
        self.assertEqual({row["structure"] for row in ctx["structures"]} - {"debit_vertical", "credit_vertical", "iron_condor"}, set())
        self.assertEqual(ctx["structure_rules"]["book"], "options-shadow")
        self.assertIn("14:30", ctx["structure_rules"]["entry_cut_new_york"])
        self.assertIn("15:30", ctx["structure_rules"]["house_close_new_york"])
        single = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.house.seat(single)
        plain = self.house.snapshot(single, self.house.book_of(single))
        self.assertNotIn("structures", plain)
        self.assertTrue(all(row["ask"] <= 0.75 for row in plain["chain"]))  # the single contract's chain is as it was

    # -- positions, orders, the expiry close and the wind-down
    def held_condor(self, agent, *, bid="0.55", ask="0.62"):
        from league import structures
        from league.book import Intent

        book = self.house.book_of(agent)
        self.house.seat(agent)
        inst = structures.instrument(structures.parse("options-shadow", condor_row()).spec, "options-shadow")
        self.shadow.set_quote(inst, bid, ask)
        intent = self.house._intents(agent, book, [condor_row()])[0][0]
        self.assertEqual(book.submit([intent])[0].status, "filled")
        return book, inst

    def test_a_held_structure_shows_its_type_legs_natural_prices_and_pnl(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.shadow.set_quote(inst, "0.70", "0.75")  # the condor is worth more: buying it back costs 0.30
        book.mark()
        # Its own sale rests: 0.75 is over the bid, and within the book's 10% of the touch.
        rested = book.submit([self.house._intents(agent, book, [condor_row(action="close", limit=0.25)])[0][0]])[0]
        self.assertEqual(rested.status, "resting", rested.detail)
        ctx = self.house.snapshot(agent, book)
        row = ctx["positions"][0]
        self.assertEqual((row["structure"], row["kind"], row["symbol"], row["expiry"], row["quantity"]), ("iron_condor", "credit", "SPY", "2026-09-11", 1.0))
        key = lambda leg: leg["occ"]  # noqa: E731 - canonical order: by expiry, right, strike
        self.assertEqual(sorted(row["legs"], key=key), sorted(condor_row()["legs"], key=key))
        # The average cost carries the book's fee a share (the practice clearing fee, S1's to set for a structure's legs).
        fee = row["average_cost"] - 0.62
        self.assertTrue(0 <= fee < 0.01, fee)
        self.assertAlmostEqual(row["mark"], 0.70)
        self.assertAlmostEqual(row["natural_open"], 0.38 - fee)  # the credit received, net of the fee
        self.assertAlmostEqual(row["natural_mark"], 0.30)  # what buying it back costs at the mark
        self.assertAlmostEqual(row["pnl_usd"], round((0.70 - row["average_cost"]) * 100, 2))
        self.assertAlmostEqual(row["max_loss_usd"], round(row["average_cost"] * 100, 2))
        self.assertNotIn("occ", row)
        order = ctx["open_orders"][0]
        self.assertEqual((order["structure"], order["action"], order["natural_limit"]), ("iron_condor", "close", 0.25))

    def test_the_house_sells_a_structure_at_its_bid_from_1530_new_york_on_its_earliest_expiry_day(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.house._state["next_wake"][agent.id] = self.clock() + 10 ** 9
        own = book.submit([self.house._intents(agent, book, [condor_row(action="close", limit=0.40)])[0][0]])[0]
        self.assertEqual(own.status, "resting", own.detail)  # its own sale at 0.60, over the bid of 0.55
        self.at(THURSDAY_11_NY + 86400 + 3.75 * 3600)  # Friday 14:45 New York: the single contract's rule would sell it now
        self.house._enforce_horizon()
        self.assertIn(inst.key, book.account(agent.id).holdings)
        self.assertEqual([o.order_id for o in book.open_orders(agent.id)], [own.order_id])  # nor cancel its own sale
        self.assertFalse([e for e in self.house.ledger.iter(kinds="agent.intent", agent=agent.id) if "expiry rule" in e.payload.get("reason", "")])
        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)  # 15:36 New York
        self.shadow.set_quote(inst, "0.58", "0.66")
        self.house._enforce_horizon()
        self.assertEqual(book.account(agent.id).holdings, {})
        sold = [e.payload for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload["side"] == "sell"]
        self.assertEqual(D(sold[0]["price"]), D("0.58"))  # at the bid: its own 0.60, over the bid, was cancelled and re-priced
        self.assertIn(own.order_id, self.shadow.cancelled)
        reasons = [e.payload.get("reason") for e in self.house.ledger.iter(kinds="agent.intent", agent=agent.id)]
        self.assertTrue(any("expiry rule for structures" in str(r) for r in reasons))
        self.assertTrue(any("structure expiry rule" in e.payload.get("message", str(e.payload)) for e in self.house.ledger.iter(kinds="ops.alert")))

    def test_the_expiry_close_re_prices_each_tick_until_it_is_gone(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)  # 15:36 New York on the Friday
        self.shadow.set_quote(inst, "0.00", "0.66")  # no bid: offered for a cent
        self.house._enforce_horizon()
        first = [o for o in book.open_orders(agent.id)]
        self.assertEqual([(o.side, o.limit_price) for o in first], [("sell", D("0.01"))])
        self.at(self.clock() + 60)
        self.house._enforce_horizon()
        self.assertEqual([o.order_id for o in book.open_orders(agent.id)], [first[0].order_id])  # at or under the bid it stays
        self.shadow.set_quote(inst, "0.40", "0.66")
        self.at(self.clock() + 60)
        self.house._enforce_horizon()  # the resting cent offer is under the new bid: kept (it fills there), nothing more sent
        self.assertEqual([o.order_id for o in book.open_orders(agent.id)], [first[0].order_id])

    def test_a_dead_agents_structure_is_sold_whole_at_its_bid_in_the_session(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.shadow.set_quote(inst, "0.57", "0.64")
        self.house.kill(self.house.registry.get(agent.id), "test")
        sold = [e.payload for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload["side"] == "sell"]
        self.assertEqual((D(sold[0]["quantity"]), D(sold[0]["price"])), (D("1"), D("0.57")))
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_every_ledger_id_of_a_structures_life_fits_the_ledgers_200_characters(self):
        """A condor's instrument key is about 140 characters; an id built from it and a 34-character agent name
        would pass the ledger's 200 and the row would be refused. Every id on the House's structure paths is a
        hash (the intent's) or short: refusals, the open, the close, the expiry-day close and the wind-down."""
        from league import structures

        agent = self.house.spawn("k" + "x" * 33, "options-structures-test", STRUCTURE_AGENT, reason="test", specialty="alpaca-options")
        self.assertEqual(len(agent.id), 34)
        book = self.house.book_of(agent)
        self.house.seat(agent)
        inst = structures.instrument(structures.parse("options-shadow", condor_row()).spec, "options-shadow")
        self.assertGreater(len(inst.key), 140)
        self.shadow.set_quote(inst, "0.55", "0.62")
        single = {"occ": occ("2026-09-11", "call", 590), "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.40, "reason": "one leg"}
        intents, _ = self.house._intents(agent, book, [condor_row(), single])
        self.assertEqual(book.submit(intents)[0].status, "filled")
        book.submit(self.house._intents(agent, book, [condor_row(action="close", limit=0.40)])[0])  # rests at 0.60
        self.at(THURSDAY_11_NY + 86400 + 3.75 * 3600)
        self.house._intents(agent, book, [condor_row()])  # refused: past the entry cut
        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)
        self.shadow.set_quote(inst, "0.50", "0.66")
        self.house._state["next_wake"][agent.id] = self.clock() + 10 ** 9
        self.house._enforce_horizon()  # its own 0.60 is cancelled and the House's sale at 0.50 fills
        self.assertEqual(book.account(agent.id).holdings, {})
        other = self.house.spawn("k" + "y" * 33, "options-structures-test", STRUCTURE_AGENT, reason="test", specialty="alpaca-options")
        self.house.seat(other)
        self.at(THURSDAY_11_NY + 3600)
        later = structures.instrument(structures.parse("options-shadow", condor_row(expiry="2026-09-14")).spec, "options-shadow")
        self.shadow.set_quote(later, "0.55", "0.62")
        book.submit(self.house._intents(other, book, [condor_row(expiry="2026-09-14")])[0])
        self.house.kill(self.house.registry.get(other.id), "test")  # the wind-down sells it whole at the bid
        self.assertEqual(book.account(other.id).holdings, {})
        ids = [e.id for e in self.house.ledger.iter()]
        self.assertTrue(ids)
        self.assertLessEqual(max(len(i) for i in ids), 200)
        self.assertTrue(self.refusals(agent))

    def test_a_dead_agents_resting_sale_at_or_under_the_bid_is_kept_across_passes_and_one_over_it_re_priced(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        own = book.submit(self.house._intents(agent, book, [condor_row(action="close", limit=0.40)])[0])[0]
        self.assertEqual(own.status, "resting", own.detail)  # 0.60, over the bid of 0.55
        self.shadow.set_quote(inst, "0.62", "0.70")  # the bid rises through it: at or under the bid now, it fills there
        submitted = len(self.shadow.submitted)
        self.house.kill(self.house.registry.get(agent.id), "test")
        self.house._retry_wind_down(self.house.registry.get(agent.id), book)
        self.assertEqual([o.order_id for o in book.open_orders(agent.id)], [own.order_id])  # kept, and nothing more sent
        self.assertEqual(len(self.shadow.submitted), submitted)
        self.shadow.set_quote(inst, "0.52", "0.60")  # the bid falls under it: cancelled and re-priced at the bid
        self.house._retry_wind_down(self.house.registry.get(agent.id), book)
        self.assertIn(own.order_id, self.shadow.cancelled)
        sold = [e.payload for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload["side"] == "sell"]
        self.assertEqual((len(sold), D(sold[0]["price"])), (1, D("0.52")))
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_one_books_failure_in_the_expiry_pass_is_a_warning_and_the_next_book_still_closes(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)  # 15:36 New York on the Friday
        self.shadow.set_quote(inst, "0.58", "0.66")
        with mock.patch.object(self.house.books["alpaca-paper"], "expire_options", side_effect=RuntimeError("the venue is down")):
            self.house._enforce_horizon()  # alpaca-paper comes first
        self.assertEqual(book.account(agent.id).holdings, {})
        warned = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "alpaca-paper: the House's horizon" in str(e.payload)]
        self.assertEqual(len(warned), 1)

    def test_one_structures_failure_is_a_warning_and_the_others_still_close(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        other = self.structure_agent("krasker")
        self.house.seat(other)
        self.assertEqual(book.submit(self.house._intents(other, book, [condor_row()])[0])[0].status, "filled")  # the same condor
        real = self.house._structure_expiry_close

        def flaky(book_, agent_id, *args, **kw):
            if agent_id == agent.id:
                raise RuntimeError("its legs have no quote")
            return real(book_, agent_id, *args, **kw)

        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)  # 15:36 New York on the Friday
        self.shadow.set_quote(inst, "0.58", "0.66")
        with mock.patch.object(self.house, "_structure_expiry_close", side_effect=flaky):
            self.house._enforce_horizon()
        self.assertIn(inst.key, book.account(agent.id).holdings)  # its close failed this pass...
        self.assertEqual(book.account(other.id).holdings, {})  # ...and the other's still went
        warned = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "could not run this pass" in str(e.payload)]
        self.assertEqual(len(warned), 1)

    def test_at_the_entry_cut_resting_opens_expiring_today_are_cancelled_and_closes_stay(self):
        from league import structures

        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        later = structures.instrument(structures.parse("options-shadow", condor_row(expiry="2026-09-14")).spec, "options-shadow")
        self.shadow.set_quote(later, "0.55", "0.62")
        vertical = {"structure": "debit_vertical", "action": "open", "quantity": 1, "limit_price": 0.30, "reason": "a Friday vertical",
                    "legs": [{"occ": occ("2026-09-11", "call", 590), "role": "long"}, {"occ": occ("2026-09-11", "call", 591), "role": "short"}]}
        self.shadow.set_quote(structures.instrument(structures.parse("options-shadow", vertical).spec, "options-shadow"), "0.25", "0.32")
        rows = [vertical, condor_row(expiry="2026-09-14", limit=0.40), condor_row(action="close", limit=0.40)]
        outcomes = book.submit(self.house._intents(agent, book, rows)[0])  # opens at 0.60 under the ask, a close at 0.60 over the bid
        self.assertEqual([o.status for o in outcomes], ["resting"] * 3)
        today_open, monday_open, close = (o.order_id for o in outcomes)
        self.at(THURSDAY_11_NY + 86400 + 3.4 * 3600)  # Friday 14:24 New York: before the cut nothing is cancelled
        self.house._enforce_horizon()
        self.assertEqual(len(book.open_orders(agent.id)), 3)
        self.at(THURSDAY_11_NY + 86400 + 3.6 * 3600)  # 14:36
        self.house._enforce_horizon()
        self.assertEqual(sorted(o.order_id for o in book.open_orders(agent.id)), sorted([monday_open, close]))
        self.assertIn(today_open, self.shadow.cancelled)
        cancelled = [e.payload for e in self.house.ledger.iter(kinds="book.order") if e.payload.get("order_id") == today_open
                     and e.payload.get("status") == "cancelled"]
        self.assertIn("entry cut for structures", str(cancelled[-1]))

    def test_a_dead_agents_structure_waits_for_the_open(self):
        agent = self.structure_agent()
        book, inst = self.held_condor(agent)
        self.at(THURSDAY_11_NY + 8 * 3600)  # 19:00 New York
        self.house.kill(self.house.registry.get(agent.id), "test")
        self.assertIn(inst.key, book.account(agent.id).holdings)
        self.assertIn(inst.key, (self.house._state.get("wind_down_held") or {}).get(agent.id, {}).get("options-shadow", {}))


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

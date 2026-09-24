"""X0 (Sept 24, 2026): the real book's entry rules, read through constitution keys.

Each applies to REAL books only and to entries only (buys that open or add); with its key absent the
book is exactly as it was. The keys are the money owner's (`CONSTITUTION["allocator"]`), so they are
patched in here, never written.

Evidence (the close-the-gaps plan, gaps 2 and 6): the allocator's nine promotions to real money ran
unproven taker mechanisms (15-minute crypto momentum at 182 bps, MLB-total takers at a 7% fee) and
20-cent ETH strikes, settled -$18.62 on 16 settlements; meriwether-h7d7702 bought NO at strikes 6, 7
and 8 of one MLB total (MILPHI), which lost together.
"""

import unittest
from decimal import Decimal
from unittest.mock import patch

from ltcm.broker import Instrument

from league.book import Book, Limits
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.tests.test_book import BookCase

D = Decimal
KEYS = {"longshot_floor_real": "0.30", "real_entry_liquidity": "maker_unless_family_taker_positive", "max_event_share": "0.25"}
GAME = "KXMLBTOTAL-26SEP231840MILPHI"
OTHER_GAME = "KXMLBTOTAL-26SEP231835TORBALG2"


def event(ticker, leg="no", venue="kalshi"):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


def rules(*only):
    """The three keys (or the ones named) patched into the allocator's constitution for one test."""
    return patch.dict(CONSTITUTION["allocator"], {k: v for k, v in KEYS.items() if not only or k in only})


class RealEntryCase(BookCase):
    venue, family, real, cash = "kalshi", "kalshi", True, "1000"
    taker_record = None  # what `family_taker` answers; None is "not measured"

    def new_book(self):
        return Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=self.real, clock=self.clock,
                    family_taker=lambda agent: self.taker_record)

    def setUp(self):
        super().setUp()
        self.book.reconcile()
        # A second, larger account so the floor's own market and cluster caps (a share of all the
        # book's capital) do not bind before the rules under test do.
        self.seat("whale", usd="600", position="100", order="75")

    def quote(self, ticker, bid, ask, leg="no"):
        self.broker.set_quote(event(ticker, leg, self.venue), bid, ask)
        other = "yes" if leg == "no" else "no"
        self.broker.set_quote(event(ticker, other, self.venue), str(D(1) - D(ask)), str(D(1) - D(bid)))

    def bid(self, agent, ticker, quantity, price, *, post_only=True, leg="no"):
        return self.book.submit([self.intent(agent, event(ticker, leg, self.venue), "buy", quantity, order_type="limit",
                                             limit_price=price, post_only=post_only)])[0]


class LongshotFloorTest(RealEntryCase):
    def test_a_real_entry_under_the_real_floor_is_refused_and_says_why(self):
        self.seat("a1", usd="100", position="50", order="50")
        self.quote("KXETHD-26SEP2317-T4199.99", "0.19", "0.21", leg="yes")
        with rules("longshot_floor_real"):
            out = self.bid("a1", "KXETHD-26SEP2317-T4199.99", "10", "0.20", leg="yes")
            self.assertEqual(out.status, "refused")
            self.assertIn("0.30", out.detail)
            self.assertIn("longshot_floor_real", out.detail)
            self.assertIn("real money", out.detail)
            self.quote("KXETHD-26SEP2317-T4099.99", "0.30", "0.32", leg="yes")
            self.assertEqual(self.bid("a1", "KXETHD-26SEP2317-T4099.99", "10", "0.30", leg="yes").status, "resting")

    def test_without_the_key_the_real_floor_is_the_books_own(self):
        self.seat("a1", usd="100", position="50", order="50")
        self.quote("KXETHD-26SEP2317-T4199.99", "0.19", "0.21", leg="yes")
        self.assertEqual(self.bid("a1", "KXETHD-26SEP2317-T4199.99", "10", "0.20", leg="yes").status, "resting")

    def test_an_exit_of_a_cheap_contract_is_never_refused(self):
        self.seat("a1", usd="100", position="50", order="50")
        self.quote("KXETHD-26SEP2317-T4199.99", "0.19", "0.21", leg="yes")
        rest = self.bid("a1", "KXETHD-26SEP2317-T4199.99", "10", "0.20", leg="yes")
        self.broker.fill_resting(rest.order_id, "10")
        self.book.poll()
        with rules():
            out = self.book.submit([self.intent("a1", event("KXETHD-26SEP2317-T4199.99", "yes", self.venue), "sell", "10")])[0]
        self.assertEqual(out.status, "filled", out.detail)


class PracticeLongshotFloorTest(RealEntryCase):
    venue, real, cash = "kalshi-shadow", False, "100000"

    def test_a_practice_book_keeps_its_own_floor(self):
        self.seat("a1", usd="100", position="50", order="50")
        self.quote("KXETHD-26SEP2317-T4199.99", "0.19", "0.21", leg="yes")
        with rules():
            self.assertEqual(self.bid("a1", "KXETHD-26SEP2317-T4199.99", "10", "0.20", leg="yes").status, "resting")
            self.assertEqual(self.bid("a1", "KXETHD-26SEP2317-T4199.99", "10", "0.10", leg="yes").status, "refused")


class EntryLiquidityTest(RealEntryCase):
    TICKER = "KXMLBGAME-26SEP231840MILPHI-PHI"

    def setUp(self):
        super().setUp()
        self.seat("meriwether-h2d625d", usd="30", position="15", order="15")
        self.quote(self.TICKER, "0.70", "0.72", leg="yes")
        self.inst = event(self.TICKER, "yes", self.venue)

    def test_a_taker_entry_is_refused_until_the_familys_taker_record_is_positive(self):
        self.taker_record = {"family": "sports-favorites", "positive": False, "n": 7, "mean_log": -0.004, "bound": -0.012}
        with rules("real_entry_liquidity"):
            market = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
            self.assertEqual(market.status, "refused")
            self.assertIn("a real entry on sports-favorites must be a post-only limit until the family's pooled taker "
                          "record is positive (7 taker settlements, bound -0.012)", market.detail)
            marketable = self.bid("meriwether-h2d625d", self.TICKER, "5", "0.72", post_only=False, leg="yes")
            self.assertEqual(marketable.status, "refused")
            self.assertIn("post-only limit", marketable.detail)
            resting = self.bid("meriwether-h2d625d", self.TICKER, "5", "0.70", post_only=True, leg="yes")
            self.assertEqual(resting.status, "resting", resting.detail)

    def test_a_positive_taker_record_lets_a_taker_entry_through(self):
        self.taker_record = {"family": "sports-favorites", "positive": True, "n": 22, "mean_log": 0.01, "bound": 0.002}
        with rules("real_entry_liquidity"):
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "filled", out.detail)

    def test_an_unmeasured_family_is_not_proven(self):
        self.taker_record = None
        with rules("real_entry_liquidity"):
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("no pooled taker record is measured", out.detail)
        # And a book built without the callable (every book before the House wires it) says the same.
        self.book = Book(self.venue, self.broker, self.ledger, fees=Fees(self.family), real_money=True, clock=self.clock)
        self.book.limits["meriwether-h2d625d"] = Limits(D(15), D(15))
        self.book.reconcile()
        with rules("real_entry_liquidity"):
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("no pooled taker record is measured", out.detail)

    def test_a_record_the_house_cannot_read_is_unmeasured(self):
        def broken(agent):
            raise RuntimeError("allocator not ready")

        self.book.family_taker = broken
        with rules("real_entry_liquidity"):
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "refused")

    def test_without_the_key_a_taker_entry_is_as_before(self):
        out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "filled", out.detail)

    def test_exits_are_never_held_to_it(self):
        rest = self.bid("meriwether-h2d625d", self.TICKER, "5", "0.70", leg="yes")
        self.broker.fill_resting(rest.order_id, "5")
        self.book.poll()
        with rules():
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "sell", "5")])[0]
        self.assertEqual(out.status, "filled", out.detail)


class PracticeEntryLiquidityTest(EntryLiquidityTest):
    venue, real, cash = "kalshi-shadow", False, "100000"

    def test_a_taker_entry_is_refused_until_the_familys_taker_record_is_positive(self):
        with rules():
            out = self.book.submit([self.intent("meriwether-h2d625d", self.inst, "buy", "5")])[0]
        self.assertEqual(out.status, "filled", out.detail)  # practice books are not held to it

    test_an_unmeasured_family_is_not_proven = test_a_taker_entry_is_refused_until_the_familys_taker_record_is_positive
    test_a_record_the_house_cannot_read_is_unmeasured = test_a_taker_entry_is_refused_until_the_familys_taker_record_is_positive


class MaxEventShareTest(RealEntryCase):
    """The brief's worked example: a $30 account, NO strikes of one game at $2.40 each."""

    def setUp(self):
        super().setUp()
        self.seat("meriwether-h7d7702", usd="30", position="15", order="15")
        for strike in (6, 7, 8, 9):
            self.quote(f"{GAME}-{strike}", "0.60", "0.62")
        self.quote(f"{OTHER_GAME}-10", "0.60", "0.62")

    def test_the_fourth_strike_of_one_game_is_refused_and_another_game_passes(self):
        with rules("max_event_share"):
            for strike in (6, 7, 8):
                out = self.bid("meriwether-h7d7702", f"{GAME}-{strike}", "4", "0.60")  # $2.40 each
                self.assertEqual(out.status, "resting", out.detail)
            fourth = self.bid("meriwether-h7d7702", f"{GAME}-9", "4", "0.60")
            self.assertEqual(fourth.status, "refused")
            self.assertIn("one event may hold at most 25% of the stake", fourth.detail)
            self.assertIn(GAME, fourth.detail)
            self.assertIn("$9.60", fourth.detail)
            other = self.bid("meriwether-h7d7702", f"{OTHER_GAME}-10", "4", "0.60")
            self.assertEqual(other.status, "resting", other.detail)

    def test_holdings_count_at_cost_with_their_fees(self):
        with rules("max_event_share"):
            rest = self.bid("meriwether-h7d7702", f"{GAME}-6", "6", "0.60")
            self.broker.fill_resting(rest.order_id, "6")  # $3.60 held
            self.book.poll()
            self.assertEqual(self.bid("meriwether-h7d7702", f"{GAME}-7", "5", "0.60").status, "resting")  # $6.60
            self.assertEqual(self.bid("meriwether-h7d7702", f"{GAME}-8", "2", "0.60").status, "refused")  # $7.80 > $7.50

    def test_props_of_four_players_of_one_game_are_one_event(self):
        """Review of #226: with the event read as the ticker less its LAST segment, each player's prop was an
        event of its own and four props of one game passed the 25% cap at $9.60 of $30."""
        game = "KXMLBHIT-26SEP231940CWSKC"
        props = [f"{game}-{player}-1" for player in ("KCSPEREZ13", "KCBWITT7", "CWSLROBERT88", "CWSAVAUGHN25")]
        for ticker in props:
            self.quote(ticker, "0.60", "0.62")
        with rules("max_event_share"):
            for ticker in props[:3]:
                self.assertEqual(self.bid("meriwether-h7d7702", ticker, "4", "0.60").status, "resting")
            fourth = self.bid("meriwether-h7d7702", props[3], "4", "0.60")
        self.assertEqual(fourth.status, "refused")
        self.assertIn(f"{game} would hold $9.60", fourth.detail)

    def test_two_segment_markets_of_two_games_are_two_events(self):
        """Review of #226: a two-segment market is its own event (Kalshi's event_ticker equals its ticker); read
        as the ticker less its last segment, every game's run-in-the-first was one event, the series."""
        for ticker in ("KXMLBRFI-26SEP231940CWSKC", "KXMLBRFI-26SEP231905TORBAL"):
            self.quote(ticker, "0.60", "0.62")
        with rules("max_event_share"):
            first = self.bid("meriwether-h7d7702", "KXMLBRFI-26SEP231940CWSKC", "10", "0.60")  # $6.00 of $30
            second = self.bid("meriwether-h7d7702", "KXMLBRFI-26SEP231905TORBAL", "10", "0.60")
        self.assertEqual(first.status, "resting", first.detail)
        self.assertEqual(second.status, "resting", second.detail)

    def test_without_the_key_the_fourth_strike_passes(self):
        for strike in (6, 7, 8, 9):
            self.assertEqual(self.bid("meriwether-h7d7702", f"{GAME}-{strike}", "4", "0.60").status, "resting")

    def test_a_practice_book_is_not_held_to_it(self):
        self.book.real_money = False
        with rules("max_event_share"):
            for strike in (6, 7, 8, 9):
                self.assertEqual(self.bid("meriwether-h7d7702", f"{GAME}-{strike}", "4", "0.60").status, "resting")


class RiskLinesTest(RealEntryCase):
    def test_the_real_books_entry_rules_are_listed(self):
        self.seat("a1", usd="30", position="15", order="15")
        with rules():
            lines = self.book.risk_lines("a1")
        self.assertEqual(lines["entry_rules"], {"longshot_floor_real": 0.30, "real_entry_liquidity": "maker_unless_family_taker_positive",
                                                "max_event_share": 0.25})
        self.assertEqual(self.book.risk_lines("a1")["entry_rules"], {})  # no keys, no rules
        self.book.real_money = False
        with rules():
            self.assertEqual(self.book.risk_lines("a1")["entry_rules"], {})  # a practice book is never held to them


if __name__ == "__main__":
    unittest.main()

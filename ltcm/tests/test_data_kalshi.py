"""Kalshi public market data: cents-to-dollars conversion, the bid-only book, quotes."""

import unittest
from decimal import Decimal

from ltcm.broker import Instrument
from ltcm.data import DataError
from ltcm.data.kalshi import (
    BASE,
    KalshiMarketData,
    cents_from_dollars,
    count_field,
    dollars_from_cents,
    price_field,
)
from ltcm.tests.fakes import Clock, FakeTransport

TICKER = "KXCPI-26SEP-T3.0"
CONTRACT = Instrument("event", "CPI", "kalshi", market_id=TICKER)

CENTS_MARKET = {
    "market": {
        "ticker": TICKER,
        "event_ticker": "KXCPI-26SEP",
        "title": "Will September CPI be above 3.0%?",
        "status": "active",
        "yes_bid": 38,
        "yes_ask": 41,
        "no_bid": 59,
        "no_ask": 62,
        "last_price": 40,
        "volume": 125000,
        "volume_24h": 8400,
        "open_interest": 32000,
        "open_time": "2026-08-01T13:00:00Z",
        "close_time": "2026-10-13T13:00:00Z",
        "can_close_early": True,
        "result": "",
    }
}

FIXED_POINT_MARKET = {
    "market": {
        "ticker": TICKER,
        "event_ticker": "KXCPI-26SEP",
        "status": "active",
        "yes_bid_dollars": "0.3825",
        "yes_ask_dollars": "0.4100",
        "no_bid_dollars": "0.5900",
        "last_price_dollars": "0.4000",
        "volume_fp": "125000.00",
        "volume_24h_fp": "8400.00",
        "open_interest_fp": "32000.00",
        "close_time": "2026-10-13T13:00:00Z",
    }
}

CENTS_BOOK = {"orderbook": {"yes": [[35, 900], [38, 400]], "no": [[55, 700], [59, 250]]}}
FIXED_POINT_BOOK = {
    "orderbook_fp": {
        "yes_dollars": [["0.3500", "900.00"], ["0.3825", "400.00"]],
        "no_dollars": [["0.5500", "700.00"], ["0.5900", "250.00"]],
    }
}

MARKETS_PAGE = {
    "markets": [CENTS_MARKET["market"], FIXED_POINT_MARKET["market"]],
    "cursor": "next-page",
}
EVENTS_PAGE = {"events": [{"event_ticker": "KXCPI-26SEP", "title": "September CPI"}], "cursor": ""}


def data(routes=None):
    transport = FakeTransport(routes or {})
    return KalshiMarketData(transport, clock=Clock("2026-09-15T13:30:00Z")), transport


class MoneyTests(unittest.TestCase):
    def test_cents_to_dollars(self):
        self.assertEqual(dollars_from_cents(40), Decimal("0.4"))
        self.assertEqual(dollars_from_cents(1), Decimal("0.01"))
        self.assertEqual(dollars_from_cents(99), Decimal("0.99"))
        self.assertIsNone(dollars_from_cents(None))
        self.assertIsNone(dollars_from_cents("abc"))

    def test_dollars_to_cents(self):
        self.assertEqual(cents_from_dollars("0.40"), 40)
        self.assertEqual(cents_from_dollars(Decimal("0.01")), 1)
        self.assertEqual(cents_from_dollars("0.99"), 99)
        self.assertEqual(cents_from_dollars("1"), 100)
        self.assertEqual(cents_from_dollars("0"), 0)

    def test_dollars_to_cents_refuses_what_it_cannot_represent(self):
        with self.assertRaises(DataError):
            cents_from_dollars("0.405")  # sub-cent tick: not expressible on the legacy surface
        with self.assertRaises(DataError):
            cents_from_dollars("1.50")  # above the $1 settlement value
        with self.assertRaises(DataError):
            cents_from_dollars("-0.10")

    def test_field_readers_prefer_fixed_point_and_fall_back_to_cents(self):
        self.assertEqual(price_field({"yes_bid": 38}, "yes_bid"), Decimal("0.38"))
        self.assertEqual(
            price_field({"yes_bid": 38, "yes_bid_dollars": "0.3825"}, "yes_bid"), Decimal("0.3825")
        )
        self.assertEqual(count_field({"volume": 10}, "volume"), Decimal("10"))
        self.assertEqual(count_field({"volume": 10, "volume_fp": "10.50"}, "volume"), Decimal("10.50"))


class MarketTests(unittest.TestCase):
    def test_reads_an_integer_cent_market(self):
        source, transport = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        row = source.market(TICKER)
        self.assertEqual(row["ticker"], TICKER)
        self.assertEqual(row["yes_bid"], Decimal("0.38"))
        self.assertEqual(row["yes_ask"], Decimal("0.41"))
        self.assertEqual(row["last_price"], Decimal("0.4"))
        self.assertEqual(row["volume_24h"], Decimal("8400"))
        self.assertTrue(row["can_close_early"])
        self.assertIsNone(row["result"])
        self.assertEqual(transport.last["url"], f"{BASE}/markets/{TICKER}")

    def test_reads_a_fixed_point_market_with_a_sub_cent_tick(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": FIXED_POINT_MARKET})
        row = source.market(TICKER)
        self.assertEqual(row["yes_bid"], Decimal("0.3825"))
        self.assertEqual(row["volume"], Decimal("125000.00"))

    def test_markets_page_and_cursor(self):
        source, transport = data({f"{BASE}/markets*": MARKETS_PAGE})
        page = source.markets(event_ticker="KXCPI-26SEP", status="open", limit=5)
        self.assertEqual(len(page["markets"]), 2)
        self.assertEqual(page["cursor"], "next-page")
        query = transport.last["query"]
        self.assertEqual(query["event_ticker"], "KXCPI-26SEP")
        self.assertEqual(query["status"], "open")
        self.assertEqual(query["limit"], "5")

    def test_an_unknown_status_never_reaches_the_network(self):
        source, transport = data({f"{BASE}/markets*": MARKETS_PAGE})
        with self.assertRaises(DataError):
            source.markets(status="wishful")
        self.assertEqual(transport.calls, [])

    def test_events_page(self):
        source, transport = data({f"{BASE}/events*": EVENTS_PAGE})
        page = source.events(status="open", with_nested_markets=True)
        self.assertEqual(page["events"][0]["event_ticker"], "KXCPI-26SEP")
        self.assertEqual(transport.last["query"]["with_nested_markets"], "true")

    def test_a_bad_ticker_is_refused(self):
        source, transport = data()
        with self.assertRaises(DataError):
            source.market("../../portfolio/balance")
        self.assertEqual(transport.calls, [])


class OrderbookTests(unittest.TestCase):
    def test_cents_book_best_first_and_the_derived_yes_ask(self):
        source, _ = data({f"{BASE}/markets/{TICKER}/orderbook*": CENTS_BOOK})
        book = source.orderbook(TICKER)
        self.assertEqual(book["yes"][0], (Decimal("0.38"), Decimal("400")))
        self.assertEqual(book["no"][0], (Decimal("0.59"), Decimal("250")))
        self.assertEqual(book["yes_bid"], Decimal("0.38"))
        # Only bids rest on a Kalshi book: the best yes ask is $1.00 minus the best no bid.
        self.assertEqual(book["yes_ask"], Decimal("0.41"))

    def test_fixed_point_book(self):
        source, _ = data({f"{BASE}/markets/{TICKER}/orderbook*": FIXED_POINT_BOOK})
        book = source.orderbook(TICKER)
        self.assertEqual(book["yes_bid"], Decimal("0.3825"))
        self.assertEqual(book["yes_ask"], Decimal("0.4100"))

    def test_an_empty_side_yields_none_rather_than_a_guess(self):
        source, _ = data({f"{BASE}/markets/{TICKER}/orderbook*": {"orderbook": {"yes": [], "no": []}}})
        book = source.orderbook(TICKER)
        self.assertIsNone(book["yes_bid"])
        self.assertIsNone(book["yes_ask"])


class QuoteTests(unittest.TestCase):
    def test_quote_is_in_dollars_and_not_delayed(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        quote = source.quote(CONTRACT)
        self.assertEqual(quote.bid, Decimal("0.38"))
        self.assertEqual(quote.ask, Decimal("0.41"))
        self.assertEqual(quote.last, Decimal("0.4"))
        self.assertEqual(quote.mid, Decimal("0.395"))
        self.assertEqual(quote.reference("buy"), Decimal("0.41"))
        self.assertEqual(quote.reference("sell"), Decimal("0.38"))
        self.assertEqual(quote.source, "kalshi")
        self.assertFalse(quote.delayed)
        self.assertEqual(quote.as_of, "2026-09-15T13:30:00Z")

    def test_only_event_contracts_are_quoted(self):
        source, _ = data()
        with self.assertRaises(DataError):
            source.quote(Instrument("equity", "AAPL", "kalshi"))

    def test_a_market_with_no_prices_is_a_data_error(self):
        empty = {"market": {"ticker": TICKER, "status": "initialized"}}
        source, _ = data({f"{BASE}/markets/{TICKER}": empty})
        with self.assertRaises(DataError):
            source.quote(CONTRACT)

    def test_adv_is_the_24h_traded_value(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        self.assertEqual(source.adv_usd(CONTRACT), Decimal("8400") * Decimal("0.4"))

    def test_bars_are_empty_rather_than_wrong(self):
        source, transport = data()
        self.assertEqual(source.bars(CONTRACT), [])
        self.assertEqual(transport.calls, [])

    def test_session_is_the_equity_calendar_for_scheduling(self):
        source, _ = data()
        self.assertIsNone(source.session("2026-11-26"))
        self.assertEqual(source.session("2026-09-15").date, "2026-09-15")


if __name__ == "__main__":
    unittest.main()

"""Kalshi public market data: cents-to-dollars conversion, the bid-only book, quotes."""

import json
import unittest
import urllib.parse
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


NO_CONTRACT = Instrument("event", "CPI", "kalshi", market_id=TICKER, right="no")
YES_CONTRACT = Instrument("event", "CPI", "kalshi", market_id=TICKER, right="yes")


class NoLegQuoteTests(unittest.TestCase):
    """A `right="no"` instrument is quoted in NO dollars: the complement, sides swapped."""

    def test_the_no_quote_is_the_complement_of_the_yes_quote(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        yes = source.quote(CONTRACT)
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        no = source.quote(NO_CONTRACT)
        # yes_bid 0.38 / yes_ask 0.41 -> no_bid 0.59 / no_ask 0.62.
        self.assertEqual(no.bid, Decimal("1") - yes.ask)
        self.assertEqual(no.ask, Decimal("1") - yes.bid)
        self.assertEqual(no.last, Decimal("1") - yes.last)
        self.assertEqual(no.bid, Decimal("0.59"))
        self.assertEqual(no.ask, Decimal("0.62"))
        self.assertEqual(no.last, Decimal("0.60"))

    def test_the_two_legs_always_sum_to_a_dollar(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        no = source.quote(NO_CONTRACT)
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        yes = source.quote(CONTRACT)
        self.assertEqual(no.reference("buy") + yes.reference("sell"), Decimal("1"))
        self.assertEqual(no.reference("sell") + yes.reference("buy"), Decimal("1"))

    def test_an_explicit_yes_leg_is_quoted_like_a_bare_instrument(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        quote = source.quote(YES_CONTRACT)
        self.assertEqual((quote.bid, quote.ask), (Decimal("0.38"), Decimal("0.41")))

    def test_a_missing_yes_side_leaves_the_matching_no_side_missing(self):
        row = {"market": dict(CENTS_MARKET["market"])}
        row["market"].pop("yes_ask")
        source, _ = data({f"{BASE}/markets/{TICKER}": row})
        quote = source.quote(NO_CONTRACT)
        self.assertIsNone(quote.bid)  # no_bid = 1 - yes_ask, and there is no yes ask
        self.assertEqual(quote.ask, Decimal("0.62"))


class PriceRangeTests(unittest.TestCase):
    def test_bands_are_read_in_dollars_and_sorted(self):
        row = {"market": dict(CENTS_MARKET["market"])}
        row["market"]["price_ranges"] = [
            {"start": "0.50", "end": "0.99", "step": "0.01"},
            {"start": "0.0001", "end": "0.4999", "step": "0.0001"},
        ]
        source, _ = data({f"{BASE}/markets/{TICKER}": row})
        bands = source.price_ranges(TICKER)
        self.assertEqual(
            bands,
            [
                {"start": Decimal("0.0001"), "end": Decimal("0.4999"), "step": Decimal("0.0001")},
                {"start": Decimal("0.50"), "end": Decimal("0.99"), "step": Decimal("0.01")},
            ],
        )

    def test_unusable_bands_are_dropped_rather_than_guessed(self):
        row = {"market": dict(CENTS_MARKET["market"])}
        row["market"]["price_ranges"] = [
            {"start": "0.01", "end": "0.99"},          # no step
            {"start": "0.01", "end": "0.99", "step": "0"},   # zero step
            {"start": "0.90", "end": "0.10", "step": "0.01"},  # inverted
            {"start": "0.01", "end": "2.00", "step": "0.01"},  # above a dollar
            {"start": "0.01", "end": "0.99", "step": "0.01"},
        ]
        source, _ = data({f"{BASE}/markets/{TICKER}": row})
        self.assertEqual(len(source.price_ranges(TICKER)), 1)

    def test_a_market_without_bands_reports_none(self):
        source, _ = data({f"{BASE}/markets/{TICKER}": CENTS_MARKET})
        self.assertEqual(source.price_ranges(TICKER), [])

    def test_the_dollar_spelling_is_preferred_and_never_divided_by_a_hundred(self):
        row = {"market": dict(CENTS_MARKET["market"])}
        row["market"]["price_ranges"] = [
            {"start_dollars": "0.01", "end_dollars": "0.99", "step_dollars": "0.01",
             "start": "0.99", "end": "0.99", "step": "0.99"}
        ]
        source, _ = data({f"{BASE}/markets/{TICKER}": row})
        self.assertEqual(source.price_ranges(TICKER)[0]["start"], Decimal("0.01"))


class OrderbookFlagTests(unittest.TestCase):
    def test_orderbook_reads_ask_for_yes_leg_pricing(self):
        source, transport = data({f"{BASE}/markets/{TICKER}/orderbook*": CENTS_BOOK})
        source.orderbook(TICKER)
        self.assertEqual(transport.last["query"]["use_yes_price"], "true")


# GET /markets/orderbooks?tickers=KXMLBEXTRAS-26SEP192110SFLAD-EXTRAS&tickers=KXTTELITEMATCH-26SEP170520KKAGPO-KKA,
# the live public API on Sept 17, 2026 at 01:29 UTC, two of the first five open markets. Unedited:
# each side arrives worst price first, and a side with no bids is an empty list.
LIVE_ORDERBOOKS = {
    "orderbooks": [
        {
            "orderbook_fp": {
                "no_dollars": [["0.0100", "13.00"], ["0.2000", "1.00"], ["0.8600", "20.00"], ["0.8700", "20.00"], ["0.8800", "20.00"], ["0.8900", "20.00"]],
                "yes_dollars": [["0.0100", "25.00"], ["0.0200", "12.00"], ["0.0300", "8.00"], ["0.0500", "5.00"]],
            },
            "ticker": "KXMLBEXTRAS-26SEP192110SFLAD-EXTRAS",
        },
        {
            "orderbook_fp": {
                "no_dollars": [["0.0100", "64.00"], ["0.0200", "15.00"], ["0.0300", "9.00"], ["0.0500", "5.00"]],
                "yes_dollars": [],
            },
            "ticker": "KXTTELITEMATCH-26SEP170520KKAGPO-KKA",
        },
    ]
}
GAME = "KXMLBEXTRAS-26SEP192110SFLAD-EXTRAS"
MATCH = "KXTTELITEMATCH-26SEP170520KKAGPO-KKA"


class ManyOrderbooksTests(unittest.TestCase):
    def test_the_live_response_parses_best_level_first_on_both_legs(self):
        source, _ = data({f"{BASE}/markets/orderbooks*": LIVE_ORDERBOOKS})
        books = source.orderbooks([GAME, MATCH])
        self.assertEqual(set(books), {GAME, MATCH})
        game = books[GAME]
        self.assertEqual(game["no"][0], (Decimal("0.8900"), Decimal("20.00")), "the best NO bid, though it arrived last")
        self.assertEqual([price for price, _ in game["no"]], sorted((price for price, _ in game["no"]), reverse=True))
        self.assertEqual(game["yes"][0], (Decimal("0.0500"), Decimal("5.00")))
        self.assertEqual((game["yes_bid"], game["no_bid"]), (Decimal("0.0500"), Decimal("0.8900")))
        # The listing row for this market read yes_bid 0.05 / yes_ask 0.11 at the same moment.
        self.assertEqual((game["yes_ask"], game["no_ask"]), (Decimal("0.1100"), Decimal("0.9500")))
        match = books[MATCH]
        self.assertEqual((match["yes"], match["yes_bid"], match["no_ask"]), ([], None, None), "no YES bids: no NO ask, not a guess")
        self.assertEqual(match["yes_ask"], Decimal("0.9500"))

    def test_tickers_are_a_repeated_parameter_never_a_comma_list(self):
        source, transport = data({f"{BASE}/markets/orderbooks*": LIVE_ORDERBOOKS})
        source.orderbooks([GAME.lower(), MATCH, GAME])
        self.assertEqual(len(transport.calls), 1)
        url = transport.last["url"]
        self.assertEqual(urllib.parse.urlsplit(url).path, "/trade-api/v2/markets/orderbooks")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query, {"tickers": [GAME, MATCH]}, "upper-cased, de-duplicated, one parameter per ticker")
        self.assertNotIn(",", urllib.parse.unquote(url), "a comma-joined list comes back as one empty book")

    def test_a_long_list_is_read_one_hundred_tickers_a_call(self):
        tickers = [f"KXTEST-26SEP17-T{n}" for n in range(230)]

        def answer(method, url, body):
            asked = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["tickers"]
            return {"orderbooks": [{"ticker": t, "orderbook_fp": {"yes_dollars": [["0.04", "10"]], "no_dollars": [["0.90", "5"], ["0.95", "7"]]}} for t in asked]}

        source, transport = data({f"{BASE}/markets/orderbooks*": answer})
        books = source.orderbooks(tickers)
        sizes = [len(urllib.parse.parse_qs(urllib.parse.urlsplit(c["url"]).query)["tickers"]) for c in transport.calls]
        self.assertEqual(sizes, [100, 100, 30])
        self.assertEqual(len(books), 230)
        self.assertEqual(books["KXTEST-26SEP17-T229"]["no_bid"], Decimal("0.95"), "the best of two levels")

    def test_a_book_the_call_did_not_ask_for_is_dropped(self):
        stray = {"orderbooks": LIVE_ORDERBOOKS["orderbooks"] + [{"ticker": "KXOTHER-1", "orderbook_fp": {"yes_dollars": [], "no_dollars": []}}]}
        source, _ = data({f"{BASE}/markets/orderbooks*": stray})
        self.assertEqual(set(source.orderbooks([GAME])), {GAME})

    def test_the_read_skips_the_transport_cache(self):
        class CachingTransport:
            def __init__(self):
                self.requests = []

            def get(self, url, headers=None, timeout=None):
                raise AssertionError("a cached GET would price an order from a stale book")

            def request(self, method, url, *, headers=None, body=None, timeout=None):
                self.requests.append((method, url))
                return 200, {}, json.dumps(LIVE_ORDERBOOKS).encode("utf-8")

        transport = CachingTransport()
        books = KalshiMarketData(transport).orderbooks([GAME])
        self.assertEqual(books[GAME]["no_bid"], Decimal("0.8900"))
        self.assertEqual([method for method, _ in transport.requests], ["GET"])

    def test_a_bad_ticker_or_a_bad_payload_is_a_data_error(self):
        source, transport = data({f"{BASE}/markets/orderbooks*": {"books": []}})
        with self.assertRaises(DataError):
            source.orderbooks(["../portfolio"])
        self.assertEqual(transport.calls, [])
        with self.assertRaises(DataError):
            source.orderbooks([GAME])
        self.assertEqual(source.orderbooks([]), {})

    def test_the_single_book_reader_keeps_its_shape(self):
        source, _ = data({f"{BASE}/markets/{TICKER}/orderbook*": FIXED_POINT_BOOK})
        book = source.orderbook(TICKER)
        self.assertEqual(set(book), {"ticker", "yes", "no", "yes_bid", "yes_ask"})
        self.assertEqual((book["yes_bid"], book["yes_ask"]), (Decimal("0.3825"), Decimal("0.4100")))

"""Coinbase public market data: product ids, the public book, candles as Bars."""

import unittest
from decimal import Decimal

from woodscapital.broker import Instrument
from woodscapital.data import DataError
from woodscapital.data.coinbase import (
    GRANULARITY,
    HOST,
    MARKET,
    CoinbaseMarketData,
    product_id,
)
from woodscapital.tests.fakes import Clock, FakeTransport

BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")
BOOK_URL = HOST + MARKET + "/product_book"
PRODUCT_URL = HOST + MARKET + "/products/BTC-USD"
CANDLES_URL = HOST + MARKET + "/products/BTC-USD/candles"

BOOK = {
    "pricebook": {
        "product_id": "BTC-USD",
        "bids": [{"price": "64123.45", "size": "0.512"}],
        "asks": [{"price": "64130.10", "size": "0.301"}],
        "time": "2026-09-15T13:29:58Z",
    },
    "last": "64127.00",
    "mid_market": "64126.775",
    "spread_bps": "1.04",
}

PRODUCT = {
    "product_id": "BTC-USD",
    "price": "64127.00",
    "volume_24h": "12345.678",
    "base_increment": "0.00000001",
    "quote_increment": "0.01",
    "base_min_size": "0.000016",
    "quote_min_size": "1",
    "base_name": "Bitcoin",
    "quote_name": "US Dollar",
    "status": "online",
    "product_type": "SPOT",
    "trading_disabled": False,
    "base_currency_id": "BTC",
    "quote_currency_id": "USD",
}

#: Three daily candles, newest first as Coinbase returns them. `start` is a Unix-seconds string.
CANDLES = {
    "candles": [
        {"start": "1789430400", "low": "63000", "high": "64500", "open": "63500", "close": "64127", "volume": "900.5"},
        {"start": "1789344000", "low": "62500", "high": "64000", "open": "62800", "close": "63500", "volume": "1100.25"},
        {"start": "1789257600", "low": "62000", "high": "63200", "open": "62100", "close": "62800", "volume": "800"},
    ]
}


def data(routes=None):
    transport = FakeTransport(routes or {})
    return CoinbaseMarketData(transport, clock=Clock("2026-09-15T13:30:00Z")), transport


class ProductIdTests(unittest.TestCase):
    def test_normalizes_the_spellings_a_desk_might_use(self):
        self.assertEqual(product_id("BTC-USD"), "BTC-USD")
        self.assertEqual(product_id("btc/usd"), "BTC-USD")
        self.assertEqual(product_id("ethusd"), "ETH-USD")
        self.assertEqual(product_id(BTC), "BTC-USD")
        self.assertEqual(product_id(Instrument("crypto", "SOL-USD", "coinbase")), "SOL-USD")

    def test_refuses_anything_that_is_not_a_pair(self):
        for bad in ("", "BTC-USD-PERP", "../accounts", "BTC USD"):
            with self.assertRaises(DataError):
                product_id(bad)


class BookTests(unittest.TestCase):
    def test_top_of_book(self):
        source, transport = data({BOOK_URL + "*": BOOK})
        book = source.product_book(BTC)
        self.assertEqual(book["bids"][0], (Decimal("64123.45"), Decimal("0.512")))
        self.assertEqual(book["asks"][0], (Decimal("64130.10"), Decimal("0.301")))
        self.assertEqual(book["last"], Decimal("64127.00"))
        query = transport.last["query"]
        self.assertEqual(query["product_id"], "BTC-USD")
        self.assertEqual(query["limit"], "1")
        self.assertIn("/api/v3/brokerage/market/product_book", transport.last["path"])

    def test_quote_uses_the_public_book_and_carries_no_authorization(self):
        source, transport = data({BOOK_URL + "*": BOOK})
        quote = source.quote(BTC)
        self.assertEqual(quote.bid, Decimal("64123.45"))
        self.assertEqual(quote.ask, Decimal("64130.10"))
        self.assertEqual(quote.last, Decimal("64127.00"))
        self.assertEqual(quote.as_of, "2026-09-15T13:29:58Z")
        self.assertEqual(quote.source, "coinbase:advanced")
        self.assertFalse(quote.delayed)
        self.assertNotIn("Authorization", transport.last["headers"])

    def test_only_crypto_is_quoted(self):
        source, _ = data()
        with self.assertRaises(DataError):
            source.quote(Instrument("equity", "AAPL", "coinbase"))

    def test_an_empty_book_is_a_data_error(self):
        source, _ = data({BOOK_URL + "*": {"pricebook": {"product_id": "BTC-USD", "bids": [], "asks": []}}})
        with self.assertRaises(DataError):
            source.quote(BTC)


class ProductTests(unittest.TestCase):
    def test_single_product_has_no_wrapper_key(self):
        source, _ = data({PRODUCT_URL: PRODUCT})
        row = source.product(BTC)
        self.assertEqual(row["product_id"], "BTC-USD")
        self.assertEqual(row["price"], Decimal("64127.00"))
        self.assertEqual(row["base_increment"], Decimal("0.00000001"))
        self.assertFalse(row["trading_disabled"])

    def test_product_list(self):
        source, transport = data({HOST + MARKET + "/products*": {"products": [PRODUCT], "num_products": 1}})
        rows = source.products()
        self.assertEqual(len(rows), 1)
        self.assertEqual(transport.last["query"]["product_type"], "SPOT")


class CandleTests(unittest.TestCase):
    def test_candles_are_sorted_oldest_first(self):
        source, transport = data({CANDLES_URL + "*": CANDLES})
        rows = source.candles(BTC, interval="1d", limit=3)
        self.assertEqual([row["start"] for row in rows], [1789257600, 1789344000, 1789430400])
        query = transport.last["query"]
        self.assertEqual(query["granularity"], "ONE_DAY")
        self.assertEqual(query["limit"], "3")
        self.assertTrue(query["start"].isdigit())
        self.assertTrue(query["end"].isdigit())
        self.assertLess(int(query["start"]), int(query["end"]))

    def test_bars_carry_the_instrument_and_the_interval_length(self):
        source, _ = data({CANDLES_URL + "*": CANDLES})
        bars = source.bars(BTC, "1d", 3)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[0].instrument, BTC)
        self.assertEqual(bars[0].open, Decimal("62100"))
        self.assertEqual(bars[-1].close, Decimal("64127"))
        self.assertEqual(bars[0].start, "2026-09-13T00:00:00Z")
        self.assertEqual(bars[0].end, "2026-09-14T00:00:00Z")

    def test_granularity_table_covers_the_intervals_the_runtime_uses(self):
        for interval in ("1m", "5m", "15m", "30m", "1h", "1d"):
            self.assertIn(interval, GRANULARITY)
        source, _ = data()
        with self.assertRaises(DataError):
            source.bars(BTC, "3d", 5)

    def test_adv_is_the_mean_daily_dollar_volume(self):
        source, _ = data({CANDLES_URL + "*": CANDLES})
        expected = (
            Decimal("62800") * Decimal("800")
            + Decimal("63500") * Decimal("1100.25")
            + Decimal("64127") * Decimal("900.5")
        ) / 3
        self.assertEqual(source.adv_usd(BTC), expected)

    def test_a_broken_source_yields_none(self):
        source, _ = data({CANDLES_URL + "*": (500, {}, b"boom")})
        self.assertIsNone(source.adv_usd(BTC))


if __name__ == "__main__":
    unittest.main()

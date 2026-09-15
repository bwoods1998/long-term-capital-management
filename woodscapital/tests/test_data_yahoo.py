"""Yahoo chart parsing: a recorded fixture in, strict Bars and a delayed Quote out."""

import unittest
from decimal import Decimal

from woodscapital.broker import Instrument
from woodscapital.data import DataError
from woodscapital.data.yahoo import (
    ADV_BARS,
    CHART,
    YahooMarketData,
    _range_for,
    chart_url,
)
from woodscapital.tests.fakes import FakeTransport

AAPL = Instrument("equity", "AAPL", "alpaca")

#: A trimmed but structurally exact `v8/finance/chart` response. Timestamps are the 09:30 ET
#: opens of four September 2026 sessions; the third row is the null padding Yahoo emits for a
#: session it has no data for, and must be dropped rather than guessed at.
FIXTURE = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "AAPL",
                    "exchangeName": "NMS",
                    "instrumentType": "EQUITY",
                    "regularMarketTime": 1789479000,
                    "gmtoffset": -14400,
                    "timezone": "EDT",
                    "exchangeTimezoneName": "America/New_York",
                    "regularMarketPrice": 234.07,
                    "chartPreviousClose": 230.03,
                    "regularMarketDayHigh": 235.5,
                    "regularMarketDayLow": 229.1,
                    "regularMarketVolume": 48123456,
                    "dataGranularity": "1d",
                    "range": "1mo",
                },
                "timestamp": [1789047000, 1789133400, 1789219800, 1789392600],
                "indicators": {
                    "quote": [
                        {
                            "open": [230.5, 232.0, None, 233.1],
                            "high": [233.0, 234.5, None, 235.5],
                            "low": [229.75, 231.25, None, 229.1],
                            "close": [232.25, 233.5, None, 234.07],
                            "volume": [41000000, 39500000, None, 48123456],
                        }
                    ],
                    "adjclose": [{"adjclose": [232.25, 233.5, None, 234.07]}],
                },
            }
        ],
        "error": None,
    }
}

ERROR_FIXTURE = {
    "chart": {
        "result": None,
        "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"},
    }
}


def source(routes=None):
    transport = FakeTransport({CHART + "AAPL*": FIXTURE, **(routes or {})})
    return YahooMarketData(transport), transport


class UrlTests(unittest.TestCase):
    def test_chart_url(self):
        url = chart_url("AAPL", interval="1d", range_="1mo")
        self.assertTrue(url.startswith("https://query2.finance.yahoo.com/v8/finance/chart/AAPL?"))
        self.assertIn("range=1mo", url)
        self.assertIn("interval=1d", url)

    def test_symbols_with_punctuation_survive(self):
        self.assertIn("/BRK-B?", chart_url("BRK-B", interval="1d", range_="1d"))
        self.assertIn("/%5EGSPC?", chart_url("^GSPC", interval="1d", range_="1d").replace("^", "%5E"))
        with self.assertRaises(DataError):
            chart_url("  ", interval="1d", range_="1d")

    def test_range_grows_with_the_requested_bar_count(self):
        self.assertEqual(_range_for("1d", 5), "5d")
        self.assertEqual(_range_for("1d", 20), "1mo")
        self.assertEqual(_range_for("1d", 200), "1y")
        self.assertEqual(_range_for("1d", 10_000), "max")
        self.assertEqual(_range_for("5m", 100), "5d")

    def test_intraday_ranges_respect_yahoo_s_own_windows(self):
        # One-minute history is capped at eight days per request, whatever the caller asks for.
        self.assertEqual(_range_for("1m", 100), "1d")
        self.assertEqual(_range_for("1m", 100_000), "5d")
        # The 2m-30m band must stay inside sixty days.
        self.assertEqual(_range_for("5m", 100_000), "3mo")
        self.assertEqual(_range_for("30m", 100_000), "3mo")
        # Hourly bars are not capped, so a long history is allowed.
        self.assertEqual(_range_for("1h", 3000), "2y")


class BarTests(unittest.TestCase):
    def test_parses_the_fixture_and_drops_the_null_row(self):
        data, transport = source()
        bars = data.bars(AAPL, "1d", 10)
        self.assertEqual(len(bars), 3, "the padded null session must be dropped")
        first, last = bars[0], bars[-1]
        self.assertEqual(first.start, "2026-09-10T13:30:00Z")
        self.assertEqual(first.open, Decimal("230.5"))
        self.assertEqual(first.close, Decimal("232.25"))
        self.assertEqual(first.volume, Decimal("41000000"))
        self.assertEqual(last.close, Decimal("234.07"))
        self.assertEqual(last.instrument, AAPL)
        self.assertEqual(first.end, "2026-09-11T13:30:00Z")
        self.assertEqual(transport.last["query"]["interval"], "1d")

    def test_prices_are_decimal_never_float(self):
        data, _ = source()
        bar = data.bars(AAPL, "1d", 1)[0]
        for value in (bar.open, bar.high, bar.low, bar.close, bar.volume):
            self.assertIsInstance(value, Decimal)
        self.assertEqual(bar.dollar_volume, bar.close * bar.volume)

    def test_limit_takes_the_most_recent_bars(self):
        data, _ = source()
        self.assertEqual(len(data.bars(AAPL, "1d", 2)), 2)
        self.assertEqual(data.bars(AAPL, "1d", 1)[0].close, Decimal("234.07"))

    def test_unknown_interval_and_silly_limits_are_refused(self):
        data, _ = source()
        with self.assertRaises(DataError):
            data.bars(AAPL, "7m", 5)
        with self.assertRaises(DataError):
            data.bars(AAPL, "1d", 0)

    def test_mismatched_column_lengths_are_a_data_error(self):
        broken = {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "AAPL", "regularMarketPrice": 1},
                        "timestamp": [1789047000, 1789133400],
                        "indicators": {"quote": [{"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}]},
                    }
                ],
                "error": None,
            }
        }
        data, _ = source({CHART + "AAPL*": broken})
        with self.assertRaises(DataError):
            data.bars(AAPL, "1d", 5)

    def test_a_symbol_with_no_history_yields_no_bars(self):
        empty = {"chart": {"result": [{"meta": {"symbol": "AAPL", "regularMarketPrice": 1}}], "error": None}}
        data, _ = source({CHART + "AAPL*": empty})
        self.assertEqual(data.bars(AAPL, "1d", 5), [])


class QuoteTests(unittest.TestCase):
    def test_quote_is_labelled_delayed(self):
        data, _ = source()
        quote = data.quote(AAPL)
        self.assertTrue(quote.delayed)
        self.assertEqual(quote.source, "yahoo:delayed")
        self.assertEqual(quote.last, Decimal("234.07"))
        self.assertIsNone(quote.bid)
        self.assertIsNone(quote.ask)
        self.assertEqual(quote.as_of, "2026-09-15T13:30:00Z")
        self.assertEqual(quote.reference("buy"), Decimal("234.07"))

    def test_bid_and_ask_are_used_when_yahoo_reports_them(self):
        with_touch = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "AAPL",
                            "regularMarketPrice": 234.07,
                            "regularMarketTime": 1789479000,
                            "bid": 234.0,
                            "ask": 234.1,
                        }
                    }
                ],
                "error": None,
            }
        }
        data, _ = source({CHART + "AAPL*": with_touch})
        quote = data.quote(AAPL)
        self.assertEqual(quote.bid, Decimal("234.0"))
        self.assertEqual(quote.ask, Decimal("234.1"))
        self.assertEqual(quote.mid, Decimal("234.05"))

    def test_a_chart_error_is_raised_not_swallowed(self):
        data, _ = source({CHART + "AAPL*": ERROR_FIXTURE})
        with self.assertRaises(DataError):
            data.quote(AAPL)

    def test_a_non_200_is_a_data_error(self):
        data, _ = source({CHART + "AAPL*": (503, {}, b"busy")})
        with self.assertRaises(DataError):
            data.quote(AAPL)

    def test_a_float_timestamp_is_rejected_as_a_shape_change(self):
        odd = {
            "chart": {
                "result": [
                    {"meta": {"symbol": "AAPL", "regularMarketPrice": 1, "regularMarketTime": 1.5}}
                ],
                "error": None,
            }
        }
        data, _ = source({CHART + "AAPL*": odd})
        with self.assertRaises(DataError):
            data.quote(AAPL)


class AdvTests(unittest.TestCase):
    def test_adv_is_the_mean_dollar_volume(self):
        data, transport = source()
        adv = data.adv_usd(AAPL)
        expected = (
            Decimal("232.25") * 41000000
            + Decimal("233.5") * 39500000
            + Decimal("234.07") * 48123456
        ) / 3
        self.assertEqual(adv, expected)
        self.assertEqual(ADV_BARS, 20)

    def test_a_broken_source_yields_none_rather_than_raising(self):
        data, _ = source({CHART + "AAPL*": ERROR_FIXTURE})
        self.assertIsNone(data.adv_usd(AAPL))


class SessionTests(unittest.TestCase):
    def test_session_uses_the_local_calendar_and_makes_no_request(self):
        data, transport = source()
        self.assertTrue(data.session("2026-11-27").early_close)
        self.assertIsNone(data.session("2026-11-26"))
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()

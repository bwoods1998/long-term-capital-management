"""Kalshi's hourly candles of a series' markets (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.kalshi_candles import CANDLES_URL, MARKETS_URL, KalshiCandles, parse_candles, parse_markets
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def markets():
    """api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXHIGHNY&min_close_ts=1790208000&max_close_ts=..., recorded
    Sept 25, 2026 06:40Z (the markets of Sept 23-25, reduced to the fields read)."""
    return json.loads((FIXTURES / "kalshi_markets_kxhighny.json").read_text(encoding="utf-8"))


def candles():
    """/markets/candlesticks for four of those markets over Sept 24, 00:00-24:00Z, hourly, recorded Sept 25, 2026 06:40Z."""
    return json.loads((FIXTURES / "kalshi_candlesticks_kxhighny.json").read_text(encoding="utf-8"))


class Candles(unittest.TestCase):
    def test_the_recorded_markets(self):
        rows, cursor = parse_markets(markets())
        self.assertEqual((len(rows), cursor), (18, ""))
        first = rows[0]
        self.assertEqual((first["ticker"], first["status"], first["volume"]), ("KXHIGHNY-26SEP25-T74", "active", 7197.53))
        self.assertIsInstance(first["open"], float)

    def test_the_recorded_candles_in_dollars_oldest_first(self):
        found = parse_candles(candles())
        self.assertEqual(sorted(found), ["KXHIGHNY-26SEP24-B66.5", "KXHIGHNY-26SEP24-B68.5", "KXHIGHNY-26SEP24-T66",
                                         "KXHIGHNY-26SEP25-B69.5"])
        rows = found["KXHIGHNY-26SEP24-B68.5"]
        self.assertEqual([r["end"] for r in rows], sorted(r["end"] for r in rows))
        self.assertEqual(rows[0]["end"], 1790211600.0)  # 01:00Z: the hour 00:00-01:00
        self.assertTrue(all(0.0 <= (r["bid_close"] if r["bid_close"] is not None else 0.0) <= 1.0 for r in rows))
        with self.assertRaises(DataError):
            parse_candles({"error": "x"})

    def test_at_most_a_hundred_markets_a_request(self):
        transport = FakeTransport({CANDLES_URL: candles(), MARKETS_URL: markets()})
        client = KalshiCandles(transport)
        client.candles(["A", "B"], 1790208000, 1790294400)
        self.assertEqual(transport.calls[0]["query"], {"market_tickers": "A,B", "start_ts": "1790208000", "end_ts": "1790294400",
                                                       "period_interval": "60"})
        with self.assertRaises(DataError):
            client.candles([f"T{i}" for i in range(101)], 0, 1)
        client.markets("KXHIGHNY", closing_from=1790208000, closing_to=1790294400.5)
        self.assertEqual(transport.calls[-1]["query"], {"series_ticker": "KXHIGHNY", "min_close_ts": "1790208000",
                                                        "max_close_ts": "1790294401", "limit": "1000"})


if __name__ == "__main__":
    unittest.main()

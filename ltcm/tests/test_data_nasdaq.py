"""Nasdaq's per-stock earnings date (Sept 24, 2026): the next announcement as the page shows it now."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.nasdaq import HEADERS, HOST, Nasdaq, parse_earnings_date
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def recorded():
    """api.nasdaq.com/api/analyst/AAPL/earnings-date, recorded Sept 24, 2026 at 03:20Z."""
    return json.loads((FIXTURES / "nasdaq_earnings_date_aapl.json").read_text(encoding="utf-8"))


class EarningsDate(unittest.TestCase):
    def test_the_recorded_page(self):
        self.assertEqual(parse_earnings_date("AAPL", recorded()),
                         {"symbol": "AAPL", "date": "2026-10-29", "estimated": True, "time": None, "eps_forecast": 1.98,
                          "analysts": 8, "last_year_eps": 1.85, "announcement": "Earnings announcement* for AAPL: Oct 29, 2026"})

    def test_a_confirmed_date_its_time_and_a_loss(self):
        page = {"data": {"announcement": "Earnings announcement* for SNAP: Nov 5, 2026",
                         "reportText": "Snap Inc. is expected to report earnings on 11/05/2026 after market close. According to Zacks, "
                                       "based on 12 analysts' forecasts, the consensus EPS forecast for the quarter is ($0.05). The "
                                       "reported EPS for the same quarter last year was -$0.12."}}
        row = parse_earnings_date("SNAP", page)
        self.assertEqual((row["date"], row["estimated"], row["time"], row["eps_forecast"], row["last_year_eps"]),
                         ("2026-11-05", False, "after_close", -0.05, -0.12))

    def test_a_page_without_a_date_or_about_another_stock_is_an_error_never_a_guess(self):
        with self.assertRaises(DataError) as caught:
            parse_earnings_date("SPY", {"data": {"announcement": "", "reportText": "No earnings data is available."}})
        self.assertIn("names no date", str(caught.exception))
        with self.assertRaises(DataError):
            parse_earnings_date("MSFT", recorded())
        with self.assertRaises(DataError):
            parse_earnings_date("AAPL", {"data": None, "status": {"rCode": 400}})

    def test_the_page_is_asked_with_its_own_headers(self):
        transport = FakeTransport({f"{HOST}/api/analyst/AAPL/earnings-date": recorded()})
        self.assertEqual(Nasdaq(transport).earnings_date("aapl")["date"], "2026-10-29")
        sent = transport.calls[-1]["headers"]
        self.assertEqual((sent["User-Agent"], sent["Origin"], sent["Referer"]), (HEADERS["User-Agent"], "https://www.nasdaq.com", "https://www.nasdaq.com/"))
        with self.assertRaises(DataError):
            Nasdaq(transport).earnings_date("not a symbol")


if __name__ == "__main__":
    unittest.main()

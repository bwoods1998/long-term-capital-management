"""EIA's public price tables (Sept 25, 2026), read from pages recorded that day."""

from __future__ import annotations

import unittest
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.fuel import HOST, SERIES, Fuel, parse_daily, parse_table, parse_weekly
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def gasoline() -> bytes:
    """www.eia.gov's weekly U.S. regular retail gasoline history table, recorded Sept 25, 2026 06:57Z (its last eight months)."""
    return (FIXTURES / "eia_gasoline_weekly.html").read_bytes()


def wti() -> bytes:
    """www.eia.gov/dnav/pet/hist/RWTCD.htm, the daily WTI spot table, recorded Sept 25, 2026 07:00Z (its last eight weeks)."""
    return (FIXTURES / "eia_wti_daily.html").read_bytes()


class Tables(unittest.TestCase):
    def test_the_weekly_table_by_week_end(self):
        values = parse_weekly(gasoline())
        self.assertEqual(values[-3:], [{"date": "2026-09-07", "value": 4.157}, {"date": "2026-09-14", "value": 4.319},
                                       {"date": "2026-09-21", "value": 4.478}])
        self.assertEqual([v["date"] for v in values], sorted(v["date"] for v in values))

    def test_the_daily_table_monday_to_friday_and_empty_days_left_out(self):
        values = parse_daily(wti())
        self.assertEqual(values[-2:], [{"date": "2026-09-21", "value": 96.97}, {"date": "2026-09-22", "value": 96.41}])
        self.assertNotIn("2026-09-07", [v["date"] for v in values])  # Labor Day: no price
        self.assertIn({"date": "2026-09-08", "value": 94.21}, values)

    def test_the_release_dates_and_a_page_without_values(self):
        table = parse_table(gasoline(), "weekly")
        self.assertEqual((table["release_date"], table["next_release"]), ("2026-09-22", "2026-09-29"))
        with self.assertRaises(DataError):
            parse_table(b"<html><body>Service unavailable</body></html>", "daily")

    def test_a_series_with_its_latest_and_recent_values(self):
        transport = FakeTransport({HOST + SERIES["GASOLINE"][0]: gasoline(), HOST + SERIES["WTI"][0]: wti()})
        fuel = Fuel(transport)
        row = fuel.series("WTI")
        self.assertEqual((row["latest"], row["unit"], row["frequency"], len(row["recent"])),
                         ({"date": "2026-09-22", "value": 96.41}, "dollars per barrel", "daily", 10))
        self.assertEqual(row["source"], "U.S. Energy Information Administration")
        self.assertEqual(fuel.series("GASOLINE")["latest"]["value"], 4.478)
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)
        with self.assertRaises(DataError):
            fuel.series("AAA")


if __name__ == "__main__":
    unittest.main()

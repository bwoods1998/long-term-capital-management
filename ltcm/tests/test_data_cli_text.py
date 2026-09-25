"""The NWS's raw Daily Climate Report text (Sept 25, 2026), read from products recorded that day."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.cli_text import FILES, HOST, ClimateText, issue_time, parse_cli
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def product(station: str) -> bytes:
    """tgftp.nws.noaa.gov/data/raw/cd/<file>.txt for KNYC (the final report, 06:33Z Sept 25), KDEN (the afternoon's preliminary
    one, 23:30Z Sept 24) and KMDW, recorded Sept 25, 2026 06:45Z."""
    return (FIXTURES / f"nws_cli_{station.lower()}.txt").read_bytes()


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class Reports(unittest.TestCase):
    def test_the_final_report_of_yesterday(self):
        report = parse_cli(product("KNYC"))
        self.assertEqual((report["issued"], report["date"], report["preliminary"], report["high"], report["high_time"], report["low"],
                          report["precip_in"], report["snow_in"]),
                         ("2026-09-25T06:33:00Z", "2026-09-24", False, 66.0, "305 PM", 53.0, 0.0, 0.0))
        self.assertEqual((report["office"], report["product"]), ("KOKX", "CLINYC"))

    def test_the_preliminary_report_of_today(self):
        report = parse_cli(product("KDEN"))
        self.assertEqual((report["issued"], report["date"], report["preliminary"], report["as_of"], report["high"], report["precip_in"]),
                         ("2026-09-24T23:30:00Z", "2026-09-24", True, "0500 PM", 71.0, 0.01))

    def test_times_written_with_a_colon(self):
        self.assertEqual(parse_cli(product("KMDW"))["high_time"], "2:59 PM")

    def test_the_header_day_across_a_month_end_and_a_page_that_is_no_report(self):
        text = "CDUS41 KOKX 010433\nCLINYC\n\nCLIMATE REPORT\nNATIONAL WEATHER SERVICE NEW YORK, NY\n1233 AM EDT FRI OCT 1 2026\n"
        self.assertEqual(issue_time(text), epoch("2026-10-01T04:33:00Z"))
        text = "CDUS41 KOKX 302330\nCLINYC\n\nCLIMATE REPORT\nNATIONAL WEATHER SERVICE NEW YORK, NY\n730 PM EDT THU OCT 1 2026\n"
        self.assertEqual(issue_time(text), epoch("2026-09-30T23:30:00Z"))  # a header a day before the local date
        with self.assertRaises(DataError):
            parse_cli(b"<html>404</html>")

    def test_each_station_its_own_file(self):
        transport = FakeTransport({f"{HOST}/data/raw/cd/{FILES['KNYC']}.txt": product("KNYC")})
        self.assertEqual(ClimateText(transport).latest("KNYC")["date"], "2026-09-24")
        self.assertEqual(len(FILES), 19)  # New Orleans' file answered a redirect to a directory
        with self.assertRaises(DataError):
            ClimateText(transport).latest("KMSY")


if __name__ == "__main__":
    unittest.main()

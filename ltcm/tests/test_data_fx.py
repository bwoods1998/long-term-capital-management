"""The ECB's euro reference rates (Sept 25, 2026), read from the files recorded that day."""

from __future__ import annotations

import unittest
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.fx import DAILY_URL, HIST_90D_URL, Ecb, last_modified, parse_rates
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"
#: What www.ecb.europa.eu answered as Last-Modified for both files on Sept 25, 2026 at 06:57Z.
MODIFIED = "Thu, 24 Sep 2026 13:56:26 GMT"


def daily() -> bytes:
    """www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml, recorded Sept 25, 2026 06:57Z (the rates of Sept 24)."""
    return (FIXTURES / "ecb_eurofxref_daily.xml").read_bytes()


def last_90_days() -> bytes:
    """www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml, recorded Sept 25, 2026 06:57Z (June 29 - Sept 24, 64 days)."""
    return (FIXTURES / "ecb_eurofxref_hist_90d.xml").read_bytes()


class Rates(unittest.TestCase):
    def test_the_recorded_files(self):
        today = parse_rates(daily())
        self.assertEqual(list(today), ["2026-09-24"])
        self.assertEqual((today["2026-09-24"]["USD"], today["2026-09-24"]["JPY"]), (1.1367, 180.57))
        history = parse_rates(last_90_days())
        self.assertEqual((len(history), min(history), max(history)), (64, "2026-06-29", "2026-09-24"))
        self.assertEqual(len(history["2026-09-24"]), 29)

    def test_a_file_that_is_not_the_rates_is_an_error(self):
        for body in (b"<html>Service unavailable</html>", b'<?xml version="1.0"?><gesmes:Envelope>eurofxref</gesmes:Envelope>'):
            with self.assertRaises(DataError):
                parse_rates(body)

    def test_the_files_and_their_last_modified(self):
        transport = FakeTransport({DAILY_URL: (200, {"last-modified": MODIFIED}, daily()), HIST_90D_URL: (200, {}, last_90_days())})
        client = Ecb(transport)
        days, modified = client.daily()
        self.assertEqual((list(days), modified), (["2026-09-24"], 1790258186.0))
        self.assertIsNone(client.last_90_days()[1])
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)
        self.assertIsNone(last_modified({"last-modified": "yesterday"}))


if __name__ == "__main__":
    unittest.main()

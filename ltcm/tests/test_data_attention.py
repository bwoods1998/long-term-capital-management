"""The TSA's checkpoint numbers and the RCP approval average (Sept 24, 2026): HTML pages, parsed
defensively -- a page that changes shape is an error, never a guessed number."""

from __future__ import annotations

import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.attention import RCP_APPROVAL_URL, TSA_URL, Attention, Blocked, blocked_reason, parse_rcp_average, parse_tsa
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def tsa_page() -> bytes:
    """www.tsa.gov/travel/passenger-volumes, recorded Sept 24, 2026 at 03:18Z: its table's header and 20 newest rows."""
    return (FIXTURES / "tsa_passenger_volumes.html").read_bytes()


def rcp_wall() -> bytes:
    """What www.realclearpolling.com answered on Sept 24, 2026 (HTTP 403, its session tokens redacted)."""
    return (FIXTURES / "rcp_datadome_403.json").read_bytes()


class Tsa(unittest.TestCase):
    def test_the_recorded_table(self):
        rows = parse_tsa(tsa_page())
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0], {"date": "2026-09-22", "travelers": 2077346})
        self.assertEqual(rows[1], {"date": "2026-09-21", "travelers": 2566118})
        self.assertEqual([r["date"] for r in rows], sorted((r["date"] for r in rows), reverse=True))

    def test_a_page_that_changed_shape_is_an_error(self):
        for page in (b"<html><body>Maintenance</body></html>",
                     b"<table><tr><th>Day</th><th>Travelers</th></tr><tr><td>9/22/2026</td><td>2,077,346</td></tr></table>",
                     b"<table><tr><th>Date</th><th>Numbers</th></tr><tr><td>soon</td><td>n/a</td></tr></table>"):
            with self.assertRaises(DataError):
                parse_tsa(page)


class Rcp(unittest.TestCase):
    def test_the_bot_wall_is_blocked_never_a_page(self):
        self.assertIn("DataDome", blocked_reason(403, rcp_wall()))
        self.assertIsNone(blocked_reason(200, tsa_page()))
        transport = FakeTransport({RCP_APPROVAL_URL: (403, {"content-type": "application/json"}, rcp_wall()),
                                   TSA_URL: (200, {"content-type": "text/html"}, tsa_page())})
        with self.assertRaises(Blocked):
            Attention(transport).approval()
        self.assertEqual(Attention(transport).tsa()[0]["travelers"], 2077346)

    def test_the_average_row_when_a_page_is_served(self):
        # UNVERIFIED against a served page (the site blocked every request on Sept 24, 2026): the
        # RCP Average row as its table reads in text.
        page = ("<table><tr><th>Poll</th><th>Date</th><th>Sample</th><th>Approve</th><th>Disapprove</th><th>Spread</th></tr>"
                "<tr class='rcpAvg'><td>RCP Average</td><td>9/10 - 9/22</td><td>--</td><td>44.1</td><td>53.2</td><td>-9.1</td></tr></table>")
        self.assertEqual(parse_rcp_average(page), {"approve": 44.1, "disapprove": 53.2, "spread": -9.1, "dates": "9/10 - 9/22"})
        with self.assertRaises(DataError):
            parse_rcp_average("<html>no average here</html>")


if __name__ == "__main__":
    unittest.main()

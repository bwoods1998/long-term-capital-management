"""BLS's release calendar and BEA's release schedule (Sept 25, 2026), read from pages recorded that day."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.attention import Blocked
from ltcm.data.calendars import BEA_SCHEDULE_URL, BLS_ICS_URL, Calendars, parse_bea_schedule, parse_bls_ics, upcoming
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def bls() -> bytes:
    """www.bls.gov/schedule/news_release/bls.ics, recorded Sept 25, 2026 07:20Z (its events from Aug 1, 2026 on)."""
    return (FIXTURES / "bls_release_calendar.ics").read_bytes()


def bea() -> bytes:
    """www.bea.gov/news/schedule, recorded Sept 25, 2026 07:21Z (its schedule table)."""
    return (FIXTURES / "bea_release_schedule.html").read_bytes()


class Calendars_(unittest.TestCase):
    def test_bls_releases_in_utc_from_new_york_time(self):
        rows = parse_bls_ics(bls())
        cpi = [r for r in rows if r["release"] == "Consumer Price Index"]
        self.assertEqual(cpi[1], {"agency": "BLS", "release": "Consumer Price Index", "at": "2026-09-11T12:30:00Z", "date": "2026-09-11",
                                  "time_et": "08:30"})
        self.assertEqual(cpi[2]["at"], "2026-10-14T12:30:00Z")
        self.assertEqual([r["at"] for r in rows], sorted(r["at"] for r in rows))
        with self.assertRaises(DataError):
            parse_bls_ics(b"<html>")

    def test_bea_schedule_with_its_year_and_times(self):
        rows = parse_bea_schedule(bea())
        self.assertEqual(rows[0]["release"][:22], "GDP (Third Estimate), ")
        self.assertEqual((rows[0]["at"], rows[0]["kind"], rows[0]["time_et"]), ("2026-09-30T12:30:00Z", "press", "08:30"))
        self.assertEqual(rows[-1]["at"], "2026-12-23T13:30:00Z")  # 8:30 standard time
        with self.assertRaises(DataError):
            parse_bea_schedule(b"<html><body>Maintenance</body></html>")

    def test_the_next_sixty_days_and_a_bot_wall_is_blocked(self):
        now = datetime.fromisoformat("2026-09-25T07:30:00+00:00").timestamp()
        ahead = upcoming(parse_bls_ics(bls()), now, 60)
        self.assertEqual(ahead[0]["date"], "2026-09-25")
        self.assertTrue(all(r["date"] <= "2026-11-24" for r in ahead))
        transport = FakeTransport({BLS_ICS_URL: (403, {}, b"<html>Access Denied</html>"), BEA_SCHEDULE_URL: bea()})
        with self.assertRaises(Blocked):
            Calendars(transport).bls()
        self.assertEqual(len(Calendars(transport).bea()), 16)


if __name__ == "__main__":
    unittest.main()

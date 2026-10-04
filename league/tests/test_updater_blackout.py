"""Deployment timing at the owner's preopen wall, using the existing US calendar and padding."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.updater import schedule, session_window
from ltcm.data import DataError


def moment(text: str) -> float:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class DeploymentBlackout(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)

    def blocked(self, at: float) -> bool:
        verdict = schedule(self.base, at, history=[])
        holds = [row for row in verdict["holds"] if row["hold"] == "session"]
        if holds:
            self.assertEqual(verdict["next_eligible_ts"], holds[0]["until_ts"])
        else:
            self.assertEqual(verdict["next_eligible_ts"], at)
        return bool(holds)

    def test_one_second_before_and_at_the_preserved_padded_start(self):
        start = moment("2026-10-05T11:55:00Z")
        window = session_window(start)
        self.assertEqual(window["starts"], start)
        self.assertFalse(self.blocked(start - 1))
        self.assertTrue(self.blocked(start))
        self.assertTrue(self.blocked(start + 1))

    def test_the_entire_required_ninety_minutes_before_open_and_the_session_are_held(self):
        opened = moment("2026-10-05T13:30:00Z")
        for offset in (-90 * 60, -90 * 60 + 1, -60 * 60, -30 * 60, -1, 0, 1, 2 * 3600):
            with self.subTest(seconds_from_open=offset):
                self.assertTrue(self.blocked(opened + offset))
        self.assertTrue(self.blocked(moment("2026-10-05T19:59:59Z")))

    def test_close_and_existing_five_minute_afterclose_padding_remain_held(self):
        for stamp in ("2026-10-05T20:00:00Z", "2026-10-05T20:04:59Z"):
            with self.subTest(at=stamp):
                self.assertTrue(self.blocked(moment(stamp)))
        self.assertFalse(self.blocked(moment("2026-10-05T20:05:00Z")))

    def test_dst_changes_session_hours_without_weakening_the_conservative_floor(self):
        for day, session, closed in (("2026-10-30", "13:30-20:00Z", "20:05:00Z"),
                                     ("2026-11-02", "14:30-21:00Z", "21:05:00Z")):
            with self.subTest(day=day):
                window = session_window(moment(f"{day}T12:00:00Z"))
                self.assertEqual(window["session"], session)
                self.assertEqual(window["starts"], moment(f"{day}T11:55:00Z"))
                self.assertEqual(window["closes"], moment(f"{day}T{closed}"))
                self.assertFalse(self.blocked(window["starts"] - 1))
                self.assertTrue(self.blocked(window["starts"]))
                opened = moment(f"{day}T{session.split('-')[0]}:00Z")
                self.assertTrue(self.blocked(opened - 90 * 60))
                self.assertTrue(self.blocked(opened))
                self.assertTrue(self.blocked(window["closes"] - 1))
                self.assertFalse(self.blocked(window["closes"]))

    def test_an_early_close_keeps_the_existing_later_utc_floor(self):
        window = session_window(moment("2026-11-27T14:00:00Z"))
        self.assertEqual(window["session"], "14:30-18:00Z (an early close)")
        self.assertEqual(window["starts"], moment("2026-11-27T11:55:00Z"))
        self.assertEqual(window["closes"], moment("2026-11-27T20:05:00Z"))
        self.assertTrue(self.blocked(moment("2026-11-27T18:00:00Z")))
        self.assertTrue(self.blocked(window["closes"] - 1))
        self.assertFalse(self.blocked(window["closes"]))

    def test_closed_weekends_and_exchange_holidays_have_no_session_hold(self):
        for day in ("2026-10-03", "2026-10-04", "2026-09-07", "2026-11-26", "2026-12-25"):
            with self.subTest(day=day):
                at = moment(f"{day}T14:00:00Z")
                self.assertIsNone(session_window(at))
                self.assertFalse(self.blocked(at))

    def test_unavailable_calendar_uses_the_same_preopen_wall_and_winter_close(self):
        with mock.patch("league.updater.us_equity_session", side_effect=DataError("outside calendar")):
            window = session_window(moment("2026-10-05T12:00:00Z"))
            self.assertEqual(window["starts"], moment("2026-10-05T11:55:00Z"))
            self.assertEqual(window["closes"], moment("2026-10-05T21:05:00Z"))
            self.assertFalse(self.blocked(window["starts"] - 1))
            self.assertTrue(self.blocked(window["starts"]))
            self.assertTrue(self.blocked(moment("2026-10-05T13:30:00Z")))
            self.assertTrue(self.blocked(window["closes"] - 1))
            self.assertFalse(self.blocked(window["closes"]))

    def test_unavailable_calendar_still_leaves_weekends_closed(self):
        with mock.patch("league.updater.us_equity_session", side_effect=DataError("outside calendar")):
            for day in ("2026-10-03", "2026-10-04"):
                with self.subTest(day=day):
                    at = moment(f"{day}T14:00:00Z")
                    self.assertIsNone(session_window(at))
                    self.assertFalse(self.blocked(at))


if __name__ == "__main__":
    unittest.main()

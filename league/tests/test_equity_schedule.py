"""The equity book's clock (`league/equity/schedule.py`): the moments of a session (regular and half days), the
offsets the constitution carries over the design's, the next and previous sessions over weekends and holidays, the
sessions a lot is held through, and the phase of any moment."""

import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from league.equity import schedule as S

NY = ZoneInfo("America/New_York")
MONDAY = dt.date(2026, 10, 12)          # a session (Columbus Day: the NYSE is open)
HALF_DAY = dt.date(2026, 11, 27)        # the day after Thanksgiving: a 13:00 close


def at(day: dt.date, hh: int, mm: int, ss: int = 0) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=NY).timestamp()


def clock(t: float) -> str:
    return dt.datetime.fromtimestamp(t, NY).strftime("%H:%M:%S")


class Moments(unittest.TestCase):
    def test_a_regular_session(self):
        m = S.moments(MONDAY)
        self.assertFalse(m.early)
        self.assertEqual({k: clock(getattr(m, k)) for k in ("audit_at", "preopen", "open_at", "open_send", "entry_until",
                                                              "exit_until", "close_send", "close_until", "close_at",
                                                              "bars_at", "decide_at")},
                         {"audit_at": "08:30:00", "preopen": "09:25:00", "open_at": "09:30:00", "open_send": "09:30:30",
                          "entry_until": "09:45:00", "exit_until": "15:55:00", "close_send": "15:55:00",
                          "close_until": "15:59:30", "close_at": "16:00:00", "bars_at": "16:20:00",
                          "decide_at": "16:30:00"})
        self.assertEqual(m.day, MONDAY)

    def test_a_half_day_moves_every_close_moment(self):
        m = S.moments(HALF_DAY)
        self.assertTrue(m.early)
        self.assertEqual((clock(m.open_send), clock(m.close_send), clock(m.close_until), clock(m.close_at),
                          clock(m.bars_at), clock(m.decide_at)),
                         ("09:30:30", "12:55:00", "12:59:30", "13:00:00", "13:20:00", "13:30:00"))

    def test_no_session_no_moments(self):
        self.assertIsNone(S.moments(dt.date(2026, 10, 10)))        # a Saturday
        self.assertIsNone(S.moments(dt.date(2026, 11, 26)))        # Thanksgiving
        self.assertIsNone(S.moments(dt.date(2019, 7, 1)))          # before the computed calendar: no moments
        self.assertFalse(S.is_session("2026-12-25"))
        self.assertTrue(S.is_session("2026-12-24"))

    def test_the_constitutions_offsets_win_key_by_key(self):
        m = S.moments(MONDAY, {"entry_until_after_open_s": 600, "close_reprice_s": 20, "not_an_offset": 5})
        self.assertEqual(clock(m.entry_until), "09:40:00")
        self.assertEqual(clock(m.close_send), "15:55:00")           # a key it does not carry keeps the design's
        self.assertEqual(S.offsets_of({"close_reprice_s": 20})["close_reprice_s"], 20)
        self.assertNotIn("not_an_offset", S.offsets_of({"not_an_offset": 5}))


class Sessions(unittest.TestCase):
    def test_next_and_previous_sessions(self):
        self.assertEqual(S.next_session(dt.date(2026, 10, 9)), MONDAY)              # Friday -> Monday
        self.assertEqual(S.next_session("2026-11-25"), HALF_DAY)                    # over Thanksgiving
        self.assertEqual(S.next_session(dt.date(2026, 10, 10)), MONDAY)             # from a Saturday
        self.assertEqual(S.previous_session(MONDAY), dt.date(2026, 10, 9))
        self.assertEqual(S.previous_session(HALF_DAY), dt.date(2026, 11, 25))

    def test_sessions_held(self):
        self.assertEqual(S.sessions_between(MONDAY, MONDAY), 0)                     # bought and judged the same day
        self.assertEqual(S.sessions_between("2026-10-09", MONDAY), 1)               # Friday's close to Monday's open
        self.assertEqual(S.sessions_between("2026-10-09", "2026-10-16"), 5)
        self.assertEqual(S.sessions_between("2026-11-25", "2026-11-30"), 2)         # over a holiday and a weekend


class Phases(unittest.TestCase):
    def test_a_session_days_phases_in_order(self):
        seen = [S.phase(at(MONDAY, hh, mm, ss))[0] for hh, mm, ss in
                ((0, 5, 0), (8, 31, 0), (9, 26, 0), (9, 31, 0), (12, 0, 0), (15, 56, 0), (16, 5, 0), (16, 21, 0),
                 (16, 31, 0), (18, 0, 0))]
        self.assertEqual(seen, ["closed", "audit", "preopen", "open_window", "session", "close_window", "after_close",
                                "bars", "decide", "night"])
        self.assertEqual(seen, [p for p in S.PHASES if p in seen])
        self.assertEqual(S.phase(at(MONDAY, 12, 0))[1], MONDAY)

    def test_a_day_without_a_session_is_closed(self):
        self.assertEqual(S.phase(at(dt.date(2026, 10, 10), 12, 0)), ("closed", dt.date(2026, 10, 10)))

    def test_a_half_days_close_window(self):
        self.assertEqual(S.phase(at(HALF_DAY, 12, 56))[0], "close_window")
        self.assertEqual(S.phase(at(HALF_DAY, 13, 25))[0], "bars")

    def test_ny_day(self):
        self.assertEqual(S.ny_day(at(MONDAY, 23, 59)), MONDAY)


if __name__ == "__main__":
    unittest.main()

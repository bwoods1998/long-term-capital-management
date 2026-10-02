"""The House's job calendar: session triggers follow New York (DST, holidays, early closes); fixed ones stay in UTC."""
import unittest
from datetime import datetime, timezone

from league.ops import schedule as S
from league.ops.registry import JOBS, by_name


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Triggers(unittest.TestCase):
    def test_preopen_is_an_hour_before_the_open_in_summer_and_in_winter(self):
        summer = S.occurrences(S.session_open(-60), at("2026-10-05T00:00:00Z"), at("2026-10-05T23:59:00Z"))
        self.assertEqual([iso(t) for t in summer], ["2026-10-05T12:30:00Z"])
        # New York leaves daylight time on Sunday Nov 1, 2026: the Monday open is 14:30Z.
        winter = S.occurrences(S.session_open(-60), at("2026-11-02T00:00:00Z"), at("2026-11-02T23:59:00Z"))
        self.assertEqual([iso(t) for t in winter], ["2026-11-02T13:30:00Z"])

    def test_session_triggers_skip_weekends_and_holidays_and_follow_an_early_close(self):
        week = S.occurrences(S.session_close(10), at("2026-11-23T00:00:00Z"), at("2026-11-30T00:00:00Z"))
        # Thanksgiving (Thu Nov 26) is closed; Friday Nov 27 closes at 13:00 New York (18:00Z); no weekend session.
        self.assertEqual([iso(t) for t in week], ["2026-11-23T21:10:00Z", "2026-11-24T21:10:00Z", "2026-11-25T21:10:00Z",
                                                 "2026-11-27T18:10:00Z"])

    def test_fixed_triggers_are_utc_and_the_window_is_half_open(self):
        start, end = at("2026-10-02T23:30:00Z"), at("2026-10-04T23:30:00Z")
        self.assertEqual([iso(t) for t in S.occurrences(S.daily(23, 30), start, end)],
                         ["2026-10-03T23:30:00Z", "2026-10-04T23:30:00Z"])
        self.assertEqual(len(S.occurrences(S.hourly(5), at("2026-10-02T00:00:00Z"), at("2026-10-02T06:00:00Z"))), 6)
        self.assertEqual(S.occurrences(S.daily(1), end, start), [])

    def test_weekly_and_first_saturday_of_the_month(self):
        october = S.occurrences(S.monthly_first(5, 15), at("2026-10-01T00:00:00Z"), at("2026-12-31T00:00:00Z"))
        self.assertEqual([iso(t) for t in october], ["2026-10-03T15:00:00Z", "2026-11-07T15:00:00Z", "2026-12-05T15:00:00Z"])
        saturdays = S.occurrences(S.weekly(5, 14), at("2026-10-01T00:00:00Z"), at("2026-10-15T00:00:00Z"))
        self.assertEqual([iso(t) for t in saturdays], ["2026-10-03T14:00:00Z", "2026-10-10T14:00:00Z"])

    def test_a_year_outside_the_computed_calendar_is_a_gap_not_a_session(self):
        gaps = S.CalendarGaps()
        self.assertEqual(S.occurrences(S.session_open(), at("2101-01-05T00:00:00Z"), at("2101-01-06T00:00:00Z"), gaps=gaps), [])
        self.assertTrue(gaps.days)

    def test_in_session_and_trading_day(self):
        self.assertTrue(S.in_session(at("2026-10-05T15:00:00Z")))
        self.assertFalse(S.in_session(at("2026-10-05T02:00:00Z")))
        self.assertTrue(S.in_session(at("2026-10-05T13:10:00Z"), pad_minutes=30))
        self.assertFalse(S.trading_day(at("2026-10-04T15:00:00Z")))

    def test_the_registry_names_every_job_once_and_keeps_fixed_jobs_out_of_both_seasons_sessions(self):
        names = [job.name for job in JOBS]
        self.assertEqual(len(names), len(set(names)))
        for name in ("preopen", "economics", "scoreboard", "hygiene", "clock", "budget", "grant", "drills", "postmortem",
                     "agenda", "engineer"):
            self.assertIn(name, by_name())
        for job in JOBS:
            for trigger in job.triggers:
                minutes = trigger.at.hour * 60 + trigger.at.minute
                inside = 12 * 60 + 55 <= minutes <= 21 * 60 + 5
                if trigger.kind == "daily":
                    self.assertFalse(inside, f"{job.name} runs inside a session window")
                elif trigger.kind in ("weekly", "monthly") and inside:
                    self.assertGreaterEqual(trigger.weekday, 5, f"{job.name} runs inside a weekday session window")


if __name__ == "__main__":
    unittest.main()

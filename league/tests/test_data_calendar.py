"""The rule-based NYSE calendar, the bounded HTTP transport and the composite router."""

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from league.broker import Instrument, Quote
from league.data import (
    CONTACT_USER_AGENT,
    DataError,
    HttpTransport,
    TransportError,
    USER_AGENT,
    easter,
    iso,
    market_open_at,
    next_session,
    nth_weekday,
    nyse_early_closes,
    nyse_holidays,
    observed,
    previous_session,
    strip_html,
    to_datetime,
    us_equity_session,
)
from league.tests.broker_fakes import Clock

#: The set `portfolio_runtime/market.py` pinned after a human review of the NYSE calendar. The
#: rules here must reproduce it exactly or the port silently changed the trading year.
REVIEWED_2026_HOLIDAYS = {
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
}
REVIEWED_2026_EARLY_CLOSES = {"2026-11-27", "2026-12-24"}


class EasterTests(unittest.TestCase):
    def test_known_easters(self):
        self.assertEqual(easter(2026), date(2026, 4, 5))
        self.assertEqual(easter(2027), date(2027, 3, 28))
        self.assertEqual(easter(2028), date(2028, 4, 16))
        self.assertEqual(easter(2030), date(2030, 4, 21))

    def test_nth_weekday_and_observance(self):
        self.assertEqual(nth_weekday(2027, 1, 0, 3), date(2027, 1, 18))  # third Monday
        self.assertEqual(nth_weekday(2026, 5, 0, -1), date(2026, 5, 25))  # last Monday
        self.assertEqual(observed(date(2027, 7, 4)), date(2027, 7, 5))  # Sunday -> Monday
        self.assertEqual(observed(date(2026, 7, 4)), date(2026, 7, 3))  # Saturday -> Friday


class HolidayTests(unittest.TestCase):
    def test_matches_the_reviewed_2026_set(self):
        self.assertEqual(set(nyse_holidays(2026)), REVIEWED_2026_HOLIDAYS)
        self.assertEqual(set(nyse_early_closes(2026)), REVIEWED_2026_EARLY_CLOSES)

    def test_2027_mlk_is_the_third_monday(self):
        holidays = nyse_holidays(2027)
        self.assertIn("2027-01-18", holidays)
        self.assertEqual(holidays["2027-01-18"], "Martin Luther King, Jr. Day")
        self.assertIsNone(us_equity_session("2027-01-18"))

    def test_2028_good_friday(self):
        holidays = nyse_holidays(2028)
        self.assertIn("2028-04-14", holidays)  # Easter 2028-04-16, Good Friday two days before
        self.assertEqual(holidays["2028-04-14"], "Good Friday")
        self.assertIsNone(us_equity_session("2028-04-14"))

    def test_every_year_2026_to_2030_has_the_nine_or_ten_weekday_closures(self):
        for year in range(2026, 2031):
            holidays = nyse_holidays(year)
            self.assertGreaterEqual(len(holidays), 9, year)
            self.assertLessEqual(len(holidays), 10, year)
            for iso_day in holidays:
                self.assertLess(date.fromisoformat(iso_day).weekday(), 5, iso_day)

    def test_new_years_on_a_saturday_is_not_observed_on_the_friday_before(self):
        # 2028-01-01 is a Saturday: the NYSE does not close on 2027-12-31.
        self.assertEqual(date(2028, 1, 1).weekday(), 5)
        self.assertNotIn("2027-12-31", nyse_holidays(2027))
        self.assertNotIn("2028-01-01", nyse_holidays(2028))
        self.assertIsNotNone(us_equity_session("2027-12-31"))

    def test_years_outside_the_reviewed_window_are_refused(self):
        with self.assertRaises(DataError):
            nyse_holidays(2019)


class EarlyCloseTests(unittest.TestCase):
    def test_day_after_thanksgiving_2026_closes_early(self):
        session = us_equity_session("2026-11-27")
        self.assertIsNotNone(session)
        self.assertTrue(session.early_close)
        self.assertEqual(session.open_at, "2026-11-27T14:30:00Z")  # 09:30 EST
        self.assertEqual(session.close_at, "2026-11-27T18:00:00Z")  # 13:00 EST

    def test_christmas_eve_is_a_half_day_only_when_it_is_a_weekday(self):
        self.assertIn("2026-12-24", nyse_early_closes(2026))  # Thursday
        self.assertNotIn("2027-12-24", nyse_early_closes(2027))  # Friday, but Christmas Saturday
        self.assertIn("2027-12-24", nyse_holidays(2027))  # so the 24th is the closure itself

    def test_july_third_is_a_half_day_only_when_july_fourth_trades(self):
        self.assertEqual(date(2029, 7, 4).weekday(), 2)  # Wednesday
        self.assertIn("2029-07-03", nyse_early_closes(2029))
        self.assertEqual(date(2026, 7, 4).weekday(), 5)  # Saturday: the 3rd is the closure
        self.assertNotIn("2026-07-03", nyse_early_closes(2026))
        self.assertIn("2026-07-03", nyse_holidays(2026))

    def test_an_early_close_is_never_also_a_holiday(self):
        for year in range(2026, 2031):
            overlap = set(nyse_early_closes(year)) & set(nyse_holidays(year))
            self.assertEqual(overlap, set(), year)


class SessionTests(unittest.TestCase):
    def test_regular_session_hours(self):
        session = us_equity_session("2026-09-15")
        self.assertEqual(session.date, "2026-09-15")
        self.assertEqual(session.open_at, "2026-09-15T13:30:00Z")  # 09:30 EDT
        self.assertEqual(session.close_at, "2026-09-15T20:00:00Z")  # 16:00 EDT
        self.assertFalse(session.early_close)
        self.assertEqual(session.to_dict()["early_close"], False)

    def test_weekends_have_no_session(self):
        self.assertIsNone(us_equity_session("2026-09-19"))  # Saturday
        self.assertIsNone(us_equity_session("2026-09-20"))  # Sunday

    def test_next_and_previous_session(self):
        upcoming = next_session("2026-09-18T20:30:00Z")  # Friday evening
        self.assertEqual(upcoming.date, "2026-09-21")  # skips the weekend
        earlier = previous_session("2026-09-21T10:00:00Z")
        self.assertEqual(earlier.date, "2026-09-18")

    def test_market_open_at(self):
        self.assertFalse(market_open_at("2026-09-15T13:29:59Z"))
        self.assertTrue(market_open_at("2026-09-15T13:30:00Z"))
        self.assertTrue(market_open_at("2026-09-15T19:59:59Z"))
        self.assertFalse(market_open_at("2026-09-15T20:00:00Z"))
        self.assertFalse(market_open_at("2026-11-26T15:00:00Z"))  # Thanksgiving


class TimeTests(unittest.TestCase):
    def test_to_datetime_accepts_the_forms_the_runtime_produces(self):
        self.assertEqual(iso("2026-09-15T13:30:00Z"), "2026-09-15T13:30:00Z")
        self.assertEqual(iso("2026-09-15T13:30:00+00:00"), "2026-09-15T13:30:00Z")
        self.assertEqual(iso(0), "1970-01-01T00:00:00Z")
        self.assertEqual(iso(to_datetime("2026-09-15")), "2026-09-15T00:00:00Z")
        with self.assertRaises(DataError):
            to_datetime("not a time")
        with self.assertRaises(DataError):
            to_datetime(True)


class HttpTransportTests(unittest.TestCase):
    def test_declares_the_contact_user_agent_and_refuses_plain_http(self):
        seen = {}

        def opener(request, timeout=None):
            seen["headers"] = dict(request.headers)
            seen["method"] = request.get_method()
            return _Response(200, b"{}")

        transport = HttpTransport(opener=opener)
        transport.get("https://example.test/x")
        self.assertEqual(seen["headers"].get("User-agent"), USER_AGENT)
        # Sept 24, 2026: the default is the one contact constant, never the owner's personal address.
        self.assertEqual(USER_AGENT, CONTACT_USER_AGENT)
        self.assertNotIn("gmail", USER_AGENT)
        with self.assertRaises(DataError):
            transport.get("http://example.test/x")

    def test_caps_the_response_size(self):
        transport = HttpTransport(opener=lambda request, timeout=None: _Response(200, b"x" * 50), max_bytes=10)
        with self.assertRaises(DataError):
            transport.get("https://example.test/big")

    def test_transport_failure_raises_transport_error_not_a_status(self):
        import urllib.error

        def opener(request, timeout=None):
            raise urllib.error.URLError("boom")

        with self.assertRaises(TransportError):
            HttpTransport(opener=opener).get("https://example.test/x")

    def test_status_codes_are_returned_not_raised(self):
        transport = HttpTransport(opener=lambda request, timeout=None: _Response(404, b"gone"))
        status, _, body = transport.get("https://example.test/x")
        self.assertEqual(status, 404)
        self.assertEqual(body, b"gone")

    def test_cache_serves_inside_the_ttl_and_refetches_after_it(self):
        calls = []
        clock = Clock("2026-09-15T13:30:00Z")

        def opener(request, timeout=None):
            calls.append(request.full_url)
            return _Response(200, b'{"n": %d}' % len(calls))

        with tempfile.TemporaryDirectory() as directory:
            transport = HttpTransport(cache_dir=directory, ttl=60, opener=opener, clock=clock)
            first = transport.get("https://example.test/a")[2]
            second = transport.get("https://example.test/a")[2]
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1, "a cache hit must not reach the opener")

            clock.advance(59)
            transport.get("https://example.test/a")
            self.assertEqual(len(calls), 1, "still inside the TTL")

            clock.advance(2)
            third = transport.get("https://example.test/a")[2]
            self.assertEqual(len(calls), 2, "past the TTL the transport refetches")
            self.assertNotEqual(first, third)

            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)
            clock.advance(10_000)
            self.assertEqual(transport.purge(), 1)

    def test_a_non_200_is_never_cached(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(1)
            return _Response(500, b"nope")

        with tempfile.TemporaryDirectory() as directory:
            transport = HttpTransport(cache_dir=directory, ttl=600, opener=opener, clock=Clock())
            transport.get("https://example.test/a")
            transport.get("https://example.test/a")
            self.assertEqual(len(calls), 2)


class StripHtmlTests(unittest.TestCase):
    def test_visible_text_only(self):
        html = (
            "<html><head><title>t</title><style>p{color:red}</style></head><body>"
            "<p>First &amp; best</p><script>evil()</script><div>Second   line</div>"
            "<table><tr><td>Cell</td></tr></table></body></html>"
        )
        text = strip_html(html)
        self.assertIn("First & best", text)
        self.assertIn("Second line", text)
        self.assertIn("Cell", text)
        self.assertNotIn("evil", text)
        self.assertNotIn("color:red", text)

    def test_malformed_markup_still_returns_text(self):
        self.assertIn("hello", strip_html("<p>hello<p>"))
        self.assertEqual(strip_html(b"<p>bytes work</p>"), "bytes work")






class _Response:
    """The minimal object `urllib` hands back: a context manager with `read` and `status`."""

    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self, size=-1):
        return self._body if size is None or size < 0 else self._body[:size]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    unittest.main()


class CacheTrimTests(unittest.TestCase):
    def test_the_cache_directory_stays_under_its_cap_oldest_first_and_drops_stray_temp_files(self):
        clock = Clock("2026-09-16T06:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            transport = HttpTransport(cache_dir=directory, ttl=3600, opener=lambda request, timeout=None: _Response(200, b"x" * 1000), clock=clock, cache_cap_bytes=3500)
            for n in range(4):
                transport.get(f"https://example.test/{n}")
                clock.advance(1)
            (Path(directory) / "deadbeef.tmp").write_text("half", encoding="utf-8")
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 4, "four entries of ~1 KB each before the trim")
            removed = transport.trim(force=True)
            kept = sorted(Path(directory).glob("*.json"))
            self.assertEqual(len(kept), 2, "a 1000-byte body is ~1.5 KB once base64 and framed: two fit under 3500 bytes")
            self.assertFalse((Path(directory) / "deadbeef.tmp").exists(), "a stray temp file goes with force")
            self.assertGreaterEqual(removed, 3)
            newest = transport.cached("https://example.test/3")
            self.assertIsNotNone(newest, "the newest entry survives")
            self.assertIsNone(transport.cached("https://example.test/0"), "the oldest went first")

    def test_stores_trim_periodically_without_being_asked(self):
        from league.data import TRIM_EVERY_STORES

        clock = Clock("2026-09-16T06:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            transport = HttpTransport(cache_dir=directory, ttl=3600, opener=lambda request, timeout=None: _Response(200, b"y" * 100), clock=clock, cache_cap_bytes=1)
            for n in range(TRIM_EVERY_STORES):
                transport.get(f"https://example.test/p{n}")
            self.assertLessEqual(len(list(Path(directory).glob("*.json"))), 1, "the fiftieth store trims the directory to the cap")

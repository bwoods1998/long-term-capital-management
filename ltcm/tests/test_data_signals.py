"""Wikipedia pageviews and GDELT's news volume (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.signals import GDELT_DOC_URL, PAGEVIEWS_URL, Signals, parse_pageviews, parse_timeline
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def pageviews():
    """wikimedia.org .../per-article/en.wikipedia/all-access/user/Bitcoin/daily/20260915/20260925, recorded Sept 25, 2026 06:55Z
    (Sept 24's views already served)."""
    return json.loads((FIXTURES / "wikimedia_pageviews_bitcoin.json").read_text(encoding="utf-8"))


def pageviews_404() -> bytes:
    """What Wikimedia answers for a title with no data (HTTP 404), recorded Sept 25, 2026."""
    return (FIXTURES / "wikimedia_pageviews_404.json").read_bytes()


def timeline():
    """api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=timelinevolraw&format=json&timespan=3d, recorded Sept 25, 2026 06:57Z."""
    return json.loads((FIXTURES / "gdelt_timelinevolraw_bitcoin.json").read_text(encoding="utf-8"))


def gdelt_429() -> bytes:
    """GDELT's answer to a second request twenty seconds after the first (HTTP 429), recorded Sept 25, 2026."""
    return (FIXTURES / "gdelt_429.txt").read_bytes()


class Pageviews(unittest.TestCase):
    def test_the_recorded_answer(self):
        rows = parse_pageviews(pageviews())
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0], {"date": "2026-09-15", "views": 2668})
        self.assertEqual(rows[-1], {"date": "2026-09-24", "views": 4778})
        with self.assertRaises(DataError):
            parse_pageviews({"detail": "no"})

    def test_a_title_without_data_is_an_empty_answer_and_the_title_is_quoted(self):
        transport = FakeTransport({PAGEVIEWS_URL + "/*": (404, {"content-type": "application/problem+json"}, pageviews_404())})
        self.assertEqual(Signals(transport).pageviews("Claude (language model)", date(2026, 9, 20), date(2026, 9, 24)), [])
        self.assertTrue(transport.calls[0]["url"].endswith("/Claude%20%28language%20model%29/daily/20260920/20260924"))
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)

    def test_a_server_error_is_an_error(self):
        transport = FakeTransport({PAGEVIEWS_URL + "/*": (503, {}, b"busy")})
        with self.assertRaises(DataError):
            Signals(transport).pageviews("Bitcoin", date(2026, 9, 20), date(2026, 9, 24))


class Gdelt(unittest.TestCase):
    def test_the_recorded_timeline(self):
        rows = parse_timeline(timeline())
        self.assertEqual(len(rows), 209)
        self.assertEqual(rows[0], {"t": "2026-09-22T07:00:00Z", "articles": 3, "all_articles": 918, "share": round(3 / 918, 8)})
        self.assertEqual([r["t"] for r in rows], sorted(r["t"] for r in rows))

    def test_a_refusal_is_an_error_saying_so(self):
        transport = FakeTransport({GDELT_DOC_URL: (429, {"content-type": "text/plain"}, gdelt_429())})
        with self.assertRaises(DataError) as caught:
            Signals(transport).timeline('"federal reserve"')
        self.assertIn("HTTP 429", str(caught.exception))

    def test_asked_for_the_volume_timeline(self):
        transport = FakeTransport({GDELT_DOC_URL: timeline()})
        Signals(transport).timeline("bitcoin", "1d")
        self.assertEqual(transport.calls[0]["query"], {"query": "bitcoin", "mode": "timelinevolraw", "format": "json", "timespan": "1d"})


if __name__ == "__main__":
    unittest.main()

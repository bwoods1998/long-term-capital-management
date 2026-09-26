"""The White House's presidential actions, the Federal Register's presidential documents and Nasdaq's
trade halts (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.attention import Blocked
from ltcm.data.notices import (FEDERAL_REGISTER_URL, HALTS_URL, WHITEHOUSE_FEED_URL, Notices, parse_actions, parse_documents,
                               parse_halts)
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def actions_page(number: int = 1) -> bytes:
    """www.whitehouse.gov/presidential-actions/feed/ (page 1) and ?paged=2, recorded Sept 25, 2026 07:05Z: thirty items each,
    their full text left out."""
    return (FIXTURES / f"whitehouse_actions_feed_p{number}.xml").read_bytes()


def documents():
    """www.federalregister.gov/api/v1/documents.json, presidential documents published since Aug 25, 2026, the newest 20 of
    32 (with next_page_url), recorded Sept 25, 2026 07:10Z."""
    return json.loads((FIXTURES / "federalregister_presidential_documents.json").read_text(encoding="utf-8"))


def halts() -> bytes:
    """www.nasdaqtrader.com/rss.aspx?feed=tradehalts, recorded Sept 25, 2026 07:13Z (17 halts)."""
    return (FIXTURES / "nasdaq_trade_halts.xml").read_bytes()


class Actions(unittest.TestCase):
    def test_the_recorded_feed_newest_first_with_its_kind(self):
        rows = parse_actions(actions_page())
        self.assertEqual(len(rows), 30)
        first = rows[0]
        self.assertEqual((first["published"], first["kind"], first["categories"]), ("2026-09-18T22:02:43Z", "executive_orders",
                                                                                    ["Executive Orders"]))
        self.assertTrue(first["link"].startswith("https://www.whitehouse.gov/presidential-actions/2026/09/"))
        self.assertEqual(first["guid"], "https://www.whitehouse.gov/?p=50541")
        self.assertEqual([r["published_at"] for r in rows], sorted((r["published_at"] for r in rows), reverse=True))
        self.assertEqual({r["kind"] for r in rows} - {"executive_orders", "proclamations", "memoranda", "nominations"}, set())
        self.assertIn("America’s", rows[3]["title"])  # the feed's entity, read as text
        with self.assertRaises(DataError):
            parse_actions(b"<html>maintenance</html>")

    def test_a_page_past_the_end_is_empty_and_the_contact_agent_is_sent(self):
        transport = FakeTransport({WHITEHOUSE_FEED_URL: actions_page(), WHITEHOUSE_FEED_URL + "?paged=2": actions_page(2),
                                   WHITEHOUSE_FEED_URL + "?paged=9": (404, {}, b"<html>not found</html>")})
        notices = Notices(transport)
        self.assertEqual(notices.actions(2)[0]["published"], "2026-08-13T21:21:46Z")
        self.assertEqual(notices.actions(9), [])
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)


class Documents(unittest.TestCase):
    def test_the_recorded_answer(self):
        rows, following = parse_documents(documents())
        self.assertEqual(len(rows), 20)
        self.assertTrue(following and "page=2" in following)
        order = rows[0]
        self.assertEqual((order["document_number"], order["subtype"], order["signing_date"], order["publication_date"],
                          order["executive_order_number"]), ("2026-19555", "Executive Order", "2026-09-18", "2026-09-23", "14431"))
        self.assertEqual(rows[1]["proclamation_number"], "11069")

    def test_every_page_is_read_or_the_span_is_not_claimed(self):
        first = documents()
        last = {**documents(), "next_page_url": None}
        transport = FakeTransport({FEDERAL_REGISTER_URL: first, "https://www.federalregister.gov/api/v1/documents?*": last})
        rows = Notices(transport).documents("2026-08-25", "2026-09-25")
        self.assertEqual(len(rows), 40)
        query = transport.calls[0]["query"]
        self.assertEqual((query["conditions[type][]"], query["conditions[publication_date][gte]"], query["conditions[publication_date][lte]"]),
                         ("PRESDOCU", "2026-08-25", "2026-09-25"))
        endless = FakeTransport({FEDERAL_REGISTER_URL: first, "https://www.federalregister.gov/api/v1/documents?*": first})
        with self.assertRaises(DataError):
            Notices(endless).documents("2026-01-01", "2026-09-25", pages=2)

    def test_a_captcha_is_blocked_never_read(self):
        transport = FakeTransport({FEDERAL_REGISTER_URL: (403, {}, b"<html>unblock.federalregister.gov captcha</html>"),
                                   HALTS_URL: (429, {}, b"<html>challenge</html>")})
        with self.assertRaises(Blocked):
            Notices(transport).halts()


class Halts(unittest.TestCase):
    def test_the_recorded_feed_in_utc_oldest_first(self):
        rows = parse_halts(halts())
        self.assertEqual(len(rows), 17)
        last = rows[-1]
        self.assertEqual((last["symbol"], last["reason"], last["halted"], last["resumed_trading"]),
                         ("RPGL", "T1", "2026-09-24T23:50:00Z", None))  # 19:50 in New York
        self.assertEqual(rows[0]["halted"][:4], "2019")  # a long-standing halt stays on the feed
        with self.assertRaises(DataError):
            parse_halts(b"<rss><channel><title>Other</title></channel></rss>")


if __name__ == "__main__":
    unittest.main()

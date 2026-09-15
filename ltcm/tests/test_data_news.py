"""Headline feeds: RSS and Atom parsing, the host allowlist, and no article fetches."""

import unittest

from ltcm.data import DataError
from ltcm.data.news import (
    ALLOWED_HOSTS,
    GOOGLE_NEWS_SEARCH,
    News,
    SEC_PRESS_RELEASES,
    YAHOO_HEADLINES,
    google_news_feed,
    parse_feed,
    yahoo_symbol_feed,
)
from ltcm.tests.fakes import FakeTransport

YAHOO_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Yahoo! Finance: AAPL News</title>
    <link>https://finance.yahoo.com/quote/AAPL</link>
    <item>
      <title>Apple &amp; suppliers face a &lt;tight&gt; quarter</title>
      <link>https://finance.yahoo.com/news/apple-suppliers-123456789.html</link>
      <pubDate>Tue, 15 Sep 2026 13:04:05 +0000</pubDate>
      <description>A plain text summary.</description>
      <guid isPermaLink="false">1d2e3f4a-0000-0000-0000-000000000001</guid>
    </item>
    <item>
      <title>Second headline</title>
      <link>https://finance.yahoo.com/news/second-987654321.html</link>
      <pubDate>Mon, 14 Sep 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Broken item with no link</title>
    </item>
  </channel>
</rss>
"""

GOOGLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>"Apple earnings" - Google News</title>
  <item>
    <title>Apple beats - Stock Titan</title>
    <link>https://news.google.com/rss/articles/CBMiabcdef</link>
    <pubDate>Tue, 15 Sep 2026 11:00:00 GMT</pubDate>
    <description>&lt;a href="https://www.stocktitan.net/x"&gt;Apple beats&lt;/a&gt;</description>
    <source url="https://www.stocktitan.net">Stock Titan</source>
  </item>
</channel></rss>
"""

SEC_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>SEC Press Releases</title>
  <entry>
    <title>
      SEC Charges Firm With Fraud
    </title>
    <link rel="alternate" href="https://www.sec.gov/newsroom/press-releases/2026-140"/>
    <published>2026-09-15T14:00:00Z</published>
    <updated>2026-09-15T14:30:00Z</updated>
  </entry>
  <entry>
    <title>Second release</title>
    <link href="https://www.sec.gov/newsroom/press-releases/2026-139"/>
    <updated>2026-09-14T12:00:00Z</updated>
  </entry>
</feed>
"""


class UrlTests(unittest.TestCase):
    def test_allowlist_is_closed(self):
        self.assertEqual(
            ALLOWED_HOSTS, {"feeds.finance.yahoo.com", "www.sec.gov", "news.google.com"}
        )

    def test_symbol_and_query_urls(self):
        url = yahoo_symbol_feed("aapl")
        self.assertTrue(url.startswith(YAHOO_HEADLINES + "?"))
        self.assertIn("s=AAPL", url)
        self.assertIn("region=US", url)
        search = google_news_feed("Apple earnings")
        self.assertTrue(search.startswith(GOOGLE_NEWS_SEARCH + "?"))
        self.assertIn("q=Apple+earnings", search)
        self.assertIn("ceid=US%3Aen", search)

    def test_bad_symbols_and_queries_are_refused_before_any_request(self):
        for bad in ("", "  ", "a" * 40, "AAPL;rm -rf /"):
            with self.assertRaises(DataError):
                yahoo_symbol_feed(bad)
        with self.assertRaises(DataError):
            google_news_feed("")
        with self.assertRaises(DataError):
            google_news_feed("x" * 400)

    def test_feeds_off_the_allowlist_are_refused(self):
        transport = FakeTransport()
        news = News(transport)
        for bad in ("https://evil.test/rss", "http://www.sec.gov/x.rss", "ftp://x"):
            with self.assertRaises(DataError):
                news.feed(bad)
        self.assertEqual(transport.calls, [])


class RssTests(unittest.TestCase):
    def test_parses_yahoo_rss(self):
        rows = parse_feed(YAHOO_RSS)
        self.assertEqual(len(rows), 2, "an item with no link is skipped, not guessed")
        first = rows[0]
        self.assertEqual(first["title"], "Apple & suppliers face a quarter")
        self.assertEqual(first["url"], "https://finance.yahoo.com/news/apple-suppliers-123456789.html")
        self.assertEqual(first["published"], "2026-09-15T13:04:05Z")
        self.assertEqual(first["source"], "Yahoo! Finance: AAPL News")
        self.assertEqual(set(first), {"title", "url", "published", "source"})
        self.assertEqual(rows[1]["published"], "2026-09-14T09:00:00Z")

    def test_google_news_source_element_wins_over_the_channel_title(self):
        rows = parse_feed(GOOGLE_RSS)
        self.assertEqual(rows[0]["source"], "Stock Titan")
        self.assertEqual(rows[0]["url"], "https://news.google.com/rss/articles/CBMiabcdef")

    def test_parses_sec_atom(self):
        rows = parse_feed(SEC_ATOM)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "SEC Charges Firm With Fraud")
        self.assertEqual(rows[0]["url"], "https://www.sec.gov/newsroom/press-releases/2026-140")
        self.assertEqual(rows[0]["published"], "2026-09-15T14:00:00Z")
        self.assertEqual(rows[0]["source"], "SEC Press Releases")
        self.assertEqual(rows[1]["published"], "2026-09-14T12:00:00Z", "falls back to updated")

    def test_malformed_xml_is_a_data_error(self):
        with self.assertRaises(DataError):
            parse_feed(b"<rss><channel><item>")
        with self.assertRaises(DataError):
            parse_feed(b"<html><body>not a feed</body></html>")

    def test_an_undated_item_keeps_a_null_published(self):
        rows = parse_feed(
            b'<rss><channel><title>T</title><item><title>X</title>'
            b"<link>https://example.test/a</link></item></channel></rss>"
        )
        self.assertIsNone(rows[0]["published"])


class FetchTests(unittest.TestCase):
    def test_headlines_search_and_press_releases_each_hit_one_feed_url(self):
        transport = FakeTransport(
            {
                YAHOO_HEADLINES + "*": YAHOO_RSS,
                GOOGLE_NEWS_SEARCH + "*": GOOGLE_RSS,
                SEC_PRESS_RELEASES: SEC_ATOM,
            }
        )
        news = News(transport)
        self.assertEqual(len(news.headlines("AAPL")), 2)
        self.assertEqual(len(news.search("Apple earnings")), 1)
        self.assertEqual(len(news.sec_press_releases()), 2)
        self.assertEqual(len(transport.calls), 3, "exactly one request per feed, no article fetches")
        for call in transport.calls:
            self.assertEqual(call["method"], "GET")

    def test_limit_truncates(self):
        transport = FakeTransport({YAHOO_HEADLINES + "*": YAHOO_RSS})
        self.assertEqual(len(News(transport).headlines("AAPL", limit=1)), 1)

    def test_a_non_200_is_a_data_error(self):
        transport = FakeTransport({YAHOO_HEADLINES + "*": (503, {}, b"busy")})
        with self.assertRaises(DataError):
            News(transport).headlines("AAPL")


if __name__ == "__main__":
    unittest.main()

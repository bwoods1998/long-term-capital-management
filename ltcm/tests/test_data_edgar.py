"""EDGAR: CIK mapping, facts, submissions, filing capture with hashes, full-text search."""

import hashlib
import tempfile
import unittest

from ltcm.data import DataError, HttpTransport
from ltcm.data.edgar import (
    COMPANYFACTS_URL,
    FULL_TEXT_SEARCH_URL,
    MAX_FILING_BYTES,
    SUBMISSIONS_URL,
    TICKERS_URL,
    Edgar,
    archive_url,
    pad_cik,
)
from ltcm.tests.fakes import Clock, FakeTransport

APPLE = "0000320193"

TICKERS = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "2": {"cik_str": "junk", "ticker": "BAD", "title": "Unparseable"},
}

SUBMISSIONS = {
    "cik": "320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-26-000105", "0001140361-26-036226"],
            "filingDate": ["2026-08-01", "2026-09-10"],
            "reportDate": ["2026-06-27", "2026-09-08"],
            "acceptanceDateTime": ["2026-08-01T18:01:00.000Z", "2026-09-10T22:30:31.000Z"],
            "form": ["10-Q", "4"],
            "primaryDocument": ["aapl-20260627.htm", "xslF345X06/form4.xml"],
            "primaryDocDescription": ["10-Q", "FORM 4"],
            "items": ["", ""],
            "size": [1234567, 4681],
            "isXBRL": [1, 0],
        },
        "files": [],
    },
}

FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "description": "Total revenue",
                "units": {
                    "USD": [
                        {
                            "end": "2026-06-27",
                            "val": 94036000000,
                            "accn": "0000320193-26-000105",
                            "fy": 2026,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2026-08-01",
                        }
                    ]
                },
            }
        }
    },
}

SEARCH = {
    "took": 12,
    "hits": {
        "total": {"value": 394, "relation": "eq"},
        "hits": [
            {
                "_id": "0000320193-26-000105:aapl-20260627.htm",
                "_source": {
                    "ciks": ["0000320193"],
                    "display_names": ["Apple Inc.  (AAPL)"],
                    "file_type": "10-Q",
                    "file_date": "2026-08-01",
                    "adsh": "0000320193-26-000105",
                    "root_forms": ["10-Q"],
                },
            }
        ],
    },
}

FILING_HTML = (
    b"<html><head><style>.x{color:red}</style></head><body>"
    b"<p>Item 1A. <b>Risk Factors</b> &mdash; supply is constrained.</p>"
    b"<script>tracker()</script>"
    b"<div>Revenue rose   12%  year over year.</div>"
    b"</body></html>"
)


def edgar(routes=None):
    transport = FakeTransport(
        {
            TICKERS_URL: TICKERS,
            SUBMISSIONS_URL.format(cik=APPLE): SUBMISSIONS,
            COMPANYFACTS_URL.format(cik=APPLE): FACTS,
            FULL_TEXT_SEARCH_URL + "*": SEARCH,
            **(routes or {}),
        }
    )
    return Edgar(transport), transport


class CikTests(unittest.TestCase):
    def test_pad_cik(self):
        self.assertEqual(pad_cik(320193), APPLE)
        self.assertEqual(pad_cik("320193"), APPLE)
        self.assertEqual(pad_cik("CIK0000320193"), APPLE)
        with self.assertRaises(DataError):
            pad_cik("apple")

    def test_ticker_to_cik_pads_and_skips_junk(self):
        client, transport = edgar()
        mapping = client.ticker_to_cik()
        self.assertEqual(mapping["AAPL"], APPLE)
        self.assertEqual(mapping["NVDA"], "0001045810")
        self.assertNotIn("BAD", mapping)
        client.ticker_to_cik()
        self.assertEqual(len(transport.calls), 1, "the mapping is cached in memory")

    def test_cik_for_refuses_an_unknown_or_malformed_ticker(self):
        client, _ = edgar()
        self.assertEqual(client.cik_for("aapl"), APPLE)
        with self.assertRaises(DataError):
            client.cik_for("NOPE")
        with self.assertRaises(DataError):
            client.cik_for("../etc/passwd")


class FactsAndSubmissionsTests(unittest.TestCase):
    def test_companyfacts_requires_a_facts_block(self):
        client, transport = edgar()
        facts = client.companyfacts(320193)
        self.assertEqual(facts["entityName"], "Apple Inc.")
        self.assertIn("Revenues", facts["facts"]["us-gaap"])
        self.assertTrue(transport.last["url"].endswith(f"CIK{APPLE}.json"))
        broken, _ = edgar({COMPANYFACTS_URL.format(cik=APPLE): {"cik": 320193}})
        with self.assertRaises(DataError):
            broken.companyfacts(APPLE)

    def test_submissions_and_recent_filings_row_shape(self):
        client, _ = edgar()
        rows = client.recent_filings(APPLE, forms=["10-Q"])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["form"], "10-Q")
        self.assertEqual(row["filed"], "2026-08-01")
        self.assertEqual(
            row["url"],
            "https://www.sec.gov/Archives/edgar/data/320193/000032019326000105/aapl-20260627.htm",
        )

    def test_archive_url_uses_the_unpadded_cik_and_a_dashless_accession(self):
        url = archive_url(APPLE, "0000320193-26-000105", "aapl-20260627.htm")
        self.assertIn("/edgar/data/320193/000032019326000105/", url)
        with self.assertRaises(DataError):
            archive_url(APPLE, "not-an-accession", "x.htm")
        with self.assertRaises(DataError):
            archive_url(APPLE, "0000320193-26-000105", "../../etc/passwd")


class FilingTextTests(unittest.TestCase):
    def test_strips_html_and_hashes_the_bytes_received(self):
        url = archive_url(APPLE, "0000320193-26-000105", "aapl-20260627.htm")
        client, _ = edgar({url: (200, {"content-type": "text/html"}, FILING_HTML)})
        captured = client.filing_text(url)
        self.assertEqual(captured["url"], url)
        self.assertEqual(captured["sha256"], hashlib.sha256(FILING_HTML).hexdigest())
        self.assertIn("Item 1A. Risk Factors", captured["text"])
        self.assertIn("Revenue rose 12% year over year.", captured["text"])
        self.assertNotIn("tracker", captured["text"])
        self.assertNotIn("color:red", captured["text"])
        self.assertFalse(captured["truncated"])

    def test_text_is_capped_at_400kb_and_flagged(self):
        url = archive_url(APPLE, "0000320193-26-000105", "big.htm")
        body = b"<p>" + b"word " * 200_000 + b"</p>"
        client, _ = edgar({url: (200, {"content-type": "text/html"}, body)})
        captured = client.filing_text(url)
        self.assertEqual(len(captured["text"]), MAX_FILING_BYTES)
        self.assertTrue(captured["truncated"])
        self.assertEqual(captured["sha256"], hashlib.sha256(body).hexdigest())

    def test_plain_text_filings_are_not_run_through_the_html_stripper(self):
        url = archive_url(APPLE, "0000320193-26-000105", "notes.txt")
        client, _ = edgar({url: (200, {"content-type": "text/plain"}, b"a < b and c > d\n\nsecond")})
        captured = client.filing_text(url)
        self.assertIn("a < b and c > d", captured["text"])

    def test_only_sec_hosts_are_fetched(self):
        client, transport = edgar()
        for bad in ("https://evil.test/doc.htm", "http://www.sec.gov/Archives/x", "not a url"):
            with self.assertRaises(DataError):
                client.filing_text(bad)
        self.assertEqual(transport.calls, [])

    def test_a_non_200_is_a_data_error(self):
        url = archive_url(APPLE, "0000320193-26-000105", "gone.htm")
        client, _ = edgar({url: (404, {}, b"")})
        with self.assertRaises(DataError):
            client.filing_text(url)


class FullTextSearchTests(unittest.TestCase):
    def test_query_parameters_and_hit_shape(self):
        client, transport = edgar()
        rows = client.full_text_search(
            "supply constraint", forms=["10-q"], start="2026-01-01", end="2026-09-01"
        )
        query = transport.last["query"]
        self.assertEqual(query["q"], "supply constraint")
        self.assertEqual(query["forms"], "10-Q")
        self.assertEqual(query["startdt"], "2026-01-01")
        self.assertEqual(query["enddt"], "2026-09-01")
        self.assertEqual(query["dateRange"], "custom")
        self.assertTrue(transport.last["url"].startswith("https://efts.sec.gov/LATEST/search-index?"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accession"], "0000320193-26-000105")
        self.assertEqual(rows[0]["document"], "aapl-20260627.htm")
        self.assertEqual(rows[0]["cik"], APPLE)
        self.assertEqual(rows[0]["form"], "10-Q")
        self.assertIn("/edgar/data/320193/000032019326000105/", rows[0]["url"])

    def test_bad_inputs_never_reach_the_network(self):
        client, transport = edgar()
        with self.assertRaises(DataError):
            client.full_text_search("")
        with self.assertRaises(DataError):
            client.full_text_search("x", start="09/01/2026")
        with self.assertRaises(DataError):
            client.full_text_search("x", forms=["10-Q; DROP TABLE"])
        self.assertEqual(transport.calls, [])

    def test_no_hits_is_an_empty_list(self):
        client, _ = edgar({FULL_TEXT_SEARCH_URL + "*": {"hits": {"hits": []}}})
        self.assertEqual(client.full_text_search("nothing"), [])


class CacheTests(unittest.TestCase):
    def test_submissions_are_served_from_the_cache_inside_the_ttl(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(request.full_url)
            return _Response(200, b'{"filings": {"recent": {}}, "n": %d}' % len(calls))

        clock = Clock("2026-09-15T13:30:00Z")
        with tempfile.TemporaryDirectory() as directory:
            transport = HttpTransport(cache_dir=directory, ttl=3600, opener=opener, clock=clock)
            client = Edgar(transport)
            client.submissions(APPLE)
            client.submissions(APPLE)
            self.assertEqual(len(calls), 1)
            clock.advance(3601)
            client.submissions(APPLE)
            self.assertEqual(len(calls), 2)


class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body
        self.headers = {"Content-Type": "application/json"}

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

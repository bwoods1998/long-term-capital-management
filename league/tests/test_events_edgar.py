import datetime as dt
import tempfile
import unittest
from pathlib import Path

from league.events import edgar as E
from league.events import store as S

FIX = Path(__file__).resolve().parent / "fixtures" / "evl"
UTC = dt.timezone.utc


def fixture(name):
    return (FIX / name).read_bytes()


class CurrentFeedTest(unittest.TestCase):
    def test_8k_entries_carry_form_cik_accession_acceptance_and_items(self):
        entries = E.parse_current(fixture("current_8k.atom"))
        self.assertGreaterEqual(len(entries), 30)
        gopro = [e for e in entries if e["accession"] == "0001500435-26-000064"]
        self.assertEqual(len(gopro), 1)
        g = gopro[0]
        self.assertEqual(g["form"], "8-K")
        self.assertEqual(g["cik"], "0001500435")
        self.assertEqual(g["items"], ["2.02", "4.02", "8.01"])
        self.assertEqual(g["accepted_at"], dt.datetime(2026, 10, 16, 21, 30, 16, tzinfo=UTC))  # 17:30:16 EDT
        self.assertTrue(g["index_url"].endswith("0001500435-26-000064-index.htm"))
        # The type=8-K feed also lists amendments; the poller keeps form type exactly 8-K (PREREG section 3).
        self.assertTrue(any(e["form"] == "8-K/A" for e in entries))
        polled = E.poll_current(lambda url: fixture("current_8k.atom") if "start=0&" in url else b"", "8-K", known=())
        self.assertTrue(polled and all(e["form"] == "8-K" for e in polled))

    def test_form4_entries_are_keyed_by_accession_with_the_issuer_preferred(self):
        entries = E.parse_current(fixture("current_4.atom"))
        pages = {E.current_url("4", start=0): fixture("current_4.atom")}
        got = E.poll_current(lambda url: pages.get(url, b""), "4", known=())
        accessions = [e["accession"] for e in got]
        self.assertEqual(len(accessions), len(set(accessions)))
        roles = {e["accession"]: e["role"] for e in got}
        both = {e["accession"] for e in entries if e["role"] == "Issuer"} & {e["accession"] for e in entries if e["role"] == "Reporting"}
        self.assertTrue(both)
        self.assertTrue(all(roles[a] == "Issuer" for a in both))

    def test_polling_stops_at_known_accessions(self):
        body = fixture("current_8k.atom")
        calls = []

        def get(url):
            calls.append(url)
            return body
        all_acc = [e["accession"] for e in E.parse_current(body)]
        got = E.poll_current(get, "8-K", known=all_acc[3:])
        self.assertEqual(sorted(e["accession"] for e in got), sorted(all_acc[:3]))
        self.assertEqual(len(calls), 2)  # page 0 had new ones, page 1 (the same body here) had none: stop


class IndexPageTest(unittest.TestCase):
    def test_no_ex99_filing_reads_the_primary_8k_document(self):
        page = E.parse_index_page(fixture("index_8k_no_ex99.htm"))
        self.assertEqual(page["accepted_at"], dt.datetime(2026, 10, 16, 21, 30, 16, tzinfo=UTC))
        self.assertEqual(page["items"], ["2.02", "4.02", "8.01"])
        url, kind = E.choose_8k_document(page["documents"])
        self.assertEqual(kind, "primary")
        self.assertTrue(url.startswith("https://www.sec.gov/Archives/edgar/data/1500435/"))
        self.assertTrue(url.endswith("gpro-20261009.htm"))

    def test_ex99_filing_reads_the_lowest_numbered_exhibit(self):
        page = E.parse_index_page(fixture("index_8k_ex99.htm"))
        self.assertIn("2.02", page["items"])
        url, kind = E.choose_8k_document(page["documents"])
        self.assertEqual(kind, "EX-99.1")
        self.assertTrue(url.startswith("https://www.sec.gov/Archives/"))

    def test_ex99_ordering(self):
        docs = [{"type": "EX-99.2", "url": "https://www.sec.gov/Archives/b.htm"},
                {"type": "EX-99.1", "url": "https://www.sec.gov/Archives/a.htm"},
                {"type": "8-K", "url": "https://www.sec.gov/Archives/main.htm"}]
        self.assertEqual(E.choose_8k_document(docs), ("https://www.sec.gov/Archives/a.htm", "EX-99.1"))
        self.assertEqual(E.choose_8k_document(docs[2:]), ("https://www.sec.gov/Archives/main.htm", "primary"))
        with self.assertRaises(E.EdgarError):
            E.choose_8k_document([{"type": "GRAPHIC", "url": "https://www.sec.gov/Archives/x.jpg"}])

    def test_form4_xml_is_found_and_parsed(self):
        page = E.parse_index_page(fixture("index_4.htm"))
        url = E.choose_form4_xml(page["documents"])
        self.assertTrue(url.endswith(".xml") and "/xsl" not in url.lower())
        parsed = E.parse_form4(fixture("form4.xml"))
        self.assertEqual(len(parsed["issuer_cik"]), 10)
        self.assertTrue(parsed["owners"])
        for tx in parsed["transactions"]:
            self.assertIn(tx["acquired"], ("A", "D", None))


class DailyIndexTest(unittest.TestCase):
    def test_exact_forms_only(self):
        rows = E.parse_daily_index(fixture("form_20261016_excerpt.idx"))
        forms = {r["form"] for r in rows}
        self.assertEqual(forms, {"8-K", "4"})
        self.assertTrue(all(len(r["cik"]) == 10 and len(r["accession"]) == 20 for r in rows))
        self.assertEqual(E.daily_index_url(dt.date(2026, 10, 16)),
                         "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.20261016.idx")


class RecordTest(unittest.TestCase):
    def test_record_filing_stores_text_and_knowable_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(tmp)
            page = fixture("index_8k_no_ex99.htm")
            doc = b"<html><body><p>GoPro   reports</p><p>third quarter results</p></body></html>"

            def get(url):
                return page if url.endswith("-index.htm") else doc
            entry = {"form": "8-K", "cik": "1500435", "accession": "0001500435-26-000064", "company": "GoPro, Inc.",
                     "items": ["2.02"], "accepted_at": None, "index_url": None}
            status = E.record_filing(st, get, entry, source="current",
                                     now=dt.datetime(2026, 10, 16, 21, 33, tzinfo=UTC))
            self.assertEqual(status, "fetched")
            row = st.db.execute("SELECT * FROM filings").fetchone()
            self.assertEqual(row["accepted_at"], "2026-10-16T21:30:16Z")
            self.assertEqual(row["knowable_at"], "2026-10-16T21:40:16Z")
            self.assertEqual(row["doc_kind"], "primary")
            self.assertEqual(st.get_document(row["text_sha"]).decode(), "GoPro reports third quarter results")
            self.assertEqual(E.record_filing(st, get, entry, source="current"), "fetched")  # idempotent
            st.close()

    def test_an_amendment_is_never_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(tmp)
            self.assertEqual(E.record_filing(st, lambda u: b"", {"form": "8-K/A", "cik": "1", "accession": "x"},
                                             source="current"), "ignored")
            self.assertEqual(st.db.execute("SELECT count(*) FROM filings").fetchone()[0], 0)
            st.close()


if __name__ == "__main__":
    unittest.main()

"""The New York Fed's reference rates and the Treasury's par yield curve (Sept 24, 2026)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.rates import PAR_YIELD_URL, REFERENCE_URL, Rates, parse_par_yields, parse_reference_rates
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def recorded_rates():
    """markets.newyorkfed.org/api/rates/all/latest.json, recorded Sept 24, 2026 at 03:16Z."""
    return json.loads((FIXTURES / "nyfed_rates_latest.json").read_text(encoding="utf-8"))


def recorded_curve() -> bytes:
    """The Treasury's September 2026 par yield feed, recorded Sept 24, 2026 at 03:18Z (four of its sixteen days)."""
    return (FIXTURES / "treasury_par_yields_202609.xml").read_bytes()


class ReferenceRates(unittest.TestCase):
    def test_the_recorded_answer(self):
        rates = parse_reference_rates(recorded_rates())
        self.assertEqual(sorted(rates), ["BGCR", "EFFR", "OBFR", "SOFR", "TGCR"])  # SOFRAI is an index, not a rate here
        self.assertEqual(rates["SOFR"], {"type": "SOFR", "effective_date": "2026-09-22", "rate": 3.87, "p1": 3.8, "p25": 3.85,
                                         "p75": 3.92, "p99": 3.95, "volume_bn": 2940.0, "revised": False})
        self.assertEqual((rates["EFFR"]["target_from"], rates["EFFR"]["target_to"]), (3.75, 4.0))

    def test_an_answer_without_a_rate_is_an_error_and_a_type_without_one_is_left_out(self):
        with self.assertRaises(DataError):
            parse_reference_rates({"refRates": []})
        rates = parse_reference_rates({"refRates": [{"type": "SOFR", "effectiveDate": "2026-09-22", "percentRate": 3.87},
                                                    {"type": "EFFR", "effectiveDate": "2026-09-22", "percentRate": None}]})
        self.assertEqual(sorted(rates), ["SOFR"])

    def test_asked_with_the_contact_user_agent(self):
        transport = FakeTransport({REFERENCE_URL: recorded_rates()})
        self.assertIn("SOFR", Rates(transport).reference_rates())
        self.assertEqual(transport.calls[-1]["headers"]["User-Agent"], CONTACT_USER_AGENT)


class ParYields(unittest.TestCase):
    def test_the_recorded_curve(self):
        curves = parse_par_yields(recorded_curve())
        self.assertEqual([c["date"] for c in curves], ["2026-09-01", "2026-09-02", "2026-09-22", "2026-09-23"])
        self.assertEqual(curves[-1]["yields"]["10Y"], 5.11)
        self.assertEqual(curves[-1]["yields"]["6W"], 4.07)
        self.assertEqual(len(curves[-1]["yields"]), 14)

    def test_a_tenor_with_no_value_is_absent_and_a_page_that_is_not_the_feed_is_an_error(self):
        body = ('<feed><m:properties><d:NEW_DATE m:type="Edm.DateTime">2026-09-23T00:00:00</d:NEW_DATE>'
                '<d:BC_1_5MONTH m:null="true" /><d:BC_10YEAR m:type="Edm.Double">5.11</d:BC_10YEAR></m:properties></feed>')
        self.assertEqual(parse_par_yields(body), [{"date": "2026-09-23", "yields": {"10Y": 5.11}}])
        with self.assertRaises(DataError):
            parse_par_yields("<html>Service unavailable</html>")

    def test_asked_by_month(self):
        transport = FakeTransport({PAR_YIELD_URL + "?*": (200, {"content-type": "text/xml"}, recorded_curve())})
        self.assertEqual(len(Rates(transport).par_yields("202609")), 4)
        self.assertEqual(transport.calls[-1]["query"], {"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": "202609"})
        with self.assertRaises(DataError):
            Rates(transport).par_yields("2026-09")


if __name__ == "__main__":
    unittest.main()

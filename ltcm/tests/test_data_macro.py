"""Macro: BLS series through the keyless v2 POST, the Fed calendar, and the empty BLS schedule."""

from __future__ import annotations

import json
import unittest

from ltcm.data import DataError
from ltcm.data.macro import (
    BLS_SERIES_URL,
    DEFAULT_SERIES,
    FED_CALENDAR_URL,
    USER_AGENT,
    Macro,
    calendar_row,
    period_key,
)
from ltcm.tests.fakes import Clock, FakeTransport, TransportError

BLS = ("POST", BLS_SERIES_URL)

BLS_JSON = {
    "status": "REQUEST_SUCCEEDED", "responseTime": 90, "message": [],
    "Results": {"series": [
        {"seriesID": "CUUR0000SA0", "data": [
            {"year": "2026", "period": "M07", "periodName": "July", "value": "333.918", "footnotes": [{}]},
            {"year": "2026", "period": "M08", "periodName": "August", "latest": "true", "value": "334.980", "footnotes": [{}]},
            {"year": "2025", "period": "M13", "periodName": "Annual", "value": "322.100", "footnotes": [{"code": "P", "text": "preliminary"}]},
            {"year": "2025", "period": "M12", "periodName": "December", "value": "n/a", "footnotes": []},
        ]},
        {"seriesID": "LNS14000000", "data": [
            {"year": "2026", "period": "M08", "periodName": "August", "latest": "true", "value": "4.1", "footnotes": [{}]},
        ]},
    ]},
}

FED_EVENTS = [
    {"description": "&lt;p&gt;Meeting of September 15-16&lt;/p&gt;", "title": "FOMC Minutes", "time": "2:00 p.m.", "month": "2026-10", "days": "7", "type": "FOMC"},
    {"link": "https://www.federalreserve.gov/live-broadcast.htm", "title": "FOMC Press Conference", "time": "2:30 p.m.", "month": "2026-10", "days": "28", "type": "FOMC"},
    {"description": "&lt;p&gt;Two-day meeting, October 27 - 28&lt;/p&gt;&#10;&#10;&lt;p&gt;Press Conference&lt;/p&gt;", "title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-10", "days": "28", "type": "FOMC"},
    {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-10", "days": "27-28", "type": "FOMC"},
    {"link": "https://www.federalreserve.gov/live-broadcast.htm", "title": "FOMC Press Conference", "time": "2:30 p.m.", "month": "2026-09", "days": "16", "type": "FOMC"},
    {"title": "Beige Book", "time": "2:00 p.m.", "month": "2026-10", "days": "14", "type": "Beige"},
    {"title": "G.5 - Foreign Exchange Rates", "time": "4:15 p.m.", "month": "2026-10", "days": "1", "type": "Stat"},
    {"title": "Speech - Governor Michael S. Barr", "time": "10:05 a.m.", "month": "2026-09", "days": "23", "type": "Speeches", "live": "https://example.org/x"},
    {"title": "&lt;p&gt;&lt;strong&gt;Offices closed.&lt;/strong&gt;&lt;/p&gt;", "month": "", "day": "24", "type": "other"},
    {},
]
FED_BODY = b"\xef\xbb\xbf" + json.dumps({"events": FED_EVENTS, "announcement": []}).encode("utf-8")


class MacroCase(unittest.TestCase):
    def transport(self, overrides=None):
        routes = {BLS: BLS_JSON, FED_CALENDAR_URL: (200, {"content-type": "application/json"}, FED_BODY)}
        routes.update(overrides or {})
        return FakeTransport(routes)

    def macro(self, transport=None):
        return Macro(transport or self.transport(), clock=Clock("2026-09-18T06:30:00Z"))


class BlsTests(MacroCase):
    def test_series_come_back_newest_first_with_iso_periods(self):
        transport = self.transport()
        answer = self.macro(transport).bls_series(("CUUR0000SA0", "LNS14000000", "CES0000000001"), years=2)
        self.assertEqual(sorted(answer), ["CES0000000001", "CUUR0000SA0", "LNS14000000"])
        cpi = answer["CUUR0000SA0"]
        self.assertEqual([row["period"] for row in cpi], ["2026-08", "2026-07", "2025"], "the unusable value is dropped, the annual keeps its year")
        self.assertEqual(cpi[0], {"period": "2026-08", "value": 334.98, "period_name": "August", "latest": True, "footnotes": []})
        self.assertEqual(cpi[2]["footnotes"], ["preliminary"])
        self.assertFalse(cpi[1]["latest"])
        self.assertEqual(answer["CES0000000001"], [], "a series BLS did not answer is present and empty")
        call = transport.last
        self.assertEqual((call["method"], call["url"]), ("POST", BLS_SERIES_URL))
        self.assertEqual(call["body"], {"seriesid": ["CUUR0000SA0", "LNS14000000", "CES0000000001"], "startyear": "2025", "endyear": "2026"})
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["headers"]["User-Agent"], USER_AGENT)

    def test_the_defaults_and_the_keyless_limits(self):
        transport = self.transport()
        self.macro(transport).bls_series(years=50)
        self.assertEqual(transport.last["body"]["seriesid"], list(DEFAULT_SERIES))
        self.assertEqual(transport.last["body"]["startyear"], "2017", "ten years is the keyless window")
        self.macro(transport).bls_series([f"S{n:02d}" for n in range(40)])
        self.assertEqual(len(transport.last["body"]["seriesid"]), 25)

    def test_failures_are_data_errors_with_the_bls_message(self):
        refused = {"status": "REQUEST_NOT_PROCESSED", "responseTime": 1, "message": ["daily threshold exceeded"], "Results": {}}
        with self.assertRaises(DataError) as caught:
            self.macro(self.transport({BLS: refused})).bls_series()
        self.assertIn("daily threshold exceeded", str(caught.exception))
        with self.assertRaises(DataError):
            self.macro(self.transport({BLS: (503, {}, b"down")})).bls_series()
        with self.assertRaises(DataError):
            self.macro(self.transport({BLS: (200, {}, b"<html>")})).bls_series()
        with self.assertRaises(DataError):
            self.macro().bls_series(())

    def test_period_keys(self):
        self.assertEqual(period_key("2026", "M08"), "2026-08")
        self.assertEqual(period_key("2026", "M13"), "2026")
        self.assertEqual(period_key("2026", "Q03"), "2026-Q3")
        self.assertEqual(period_key("2026", "S01"), "2026-S1")
        self.assertEqual(period_key("2026", "A01"), "2026")
        self.assertIsNone(period_key("2026", "M14"))
        self.assertIsNone(period_key("26", "M01"))
        self.assertIsNone(period_key(None, None))


class FedTests(MacroCase):
    def test_upcoming_fomc_rows_are_soonest_first_and_the_bom_is_tolerated(self):
        transport = self.transport()
        rows = self.macro(transport).fed_calendar()
        self.assertEqual([(r["date"], r["title"]) for r in rows], [
            ("2026-10-07", "FOMC Minutes"),
            ("2026-10-27", "FOMC Meeting"),
            ("2026-10-28", "FOMC Meeting"),
            ("2026-10-28", "FOMC Press Conference"),
        ])
        self.assertEqual(rows[0]["description"], "Meeting of September 15-16", "escaped HTML is stripped")
        self.assertEqual(rows[1]["end_date"], "2026-10-28", "a day range keeps its last day")
        self.assertEqual(rows[2]["description"], "Two-day meeting, October 27 - 28 Press Conference")
        self.assertEqual(rows[3]["link"], "https://www.federalreserve.gov/live-broadcast.htm")
        self.assertEqual(rows[0]["type"], "FOMC")
        self.assertEqual(transport.last["url"], FED_CALENDAR_URL)
        self.assertEqual(transport.last["headers"]["User-Agent"], USER_AGENT)

    def test_types_past_rows_and_the_next_meeting(self):
        macro = self.macro()
        every = macro.fed_calendar(types=None)
        self.assertEqual([r["title"] for r in every][:2], ["Speech - Governor Michael S. Barr", "G.5 - Foreign Exchange Rates"])
        self.assertEqual(len(every), 7, "the malformed rows never reach a caller")
        self.assertEqual([r["date"] for r in macro.fed_calendar(include_past=True)][0], "2026-09-16")
        self.assertEqual([r["type"] for r in macro.fed_calendar(types=("beige",))], ["Beige"])
        self.assertEqual(macro.next_fomc()["date"], "2026-10-27")

    def test_an_unreachable_or_reshaped_calendar_is_an_empty_list(self):
        for payload in ((500, {}, b"down"), (200, {}, b"not json"), {"events": "junk"}, [], TransportError("dns")):
            self.assertEqual(self.macro(self.transport({FED_CALENDAR_URL: payload})).fed_calendar(), [], repr(payload))
        self.assertIsNone(self.macro(self.transport({FED_CALENDAR_URL: {"events": []}})).next_fomc())
        self.assertIsNone(calendar_row({"title": "x", "month": "2026-10", "days": "??"}))
        self.assertIsNone(calendar_row({"title": "x", "month": "2026-13", "days": "1"}))

    def test_bls_release_schedule_is_documented_as_empty(self):
        self.assertEqual(self.macro().next_releases(), [])


if __name__ == "__main__":
    unittest.main()

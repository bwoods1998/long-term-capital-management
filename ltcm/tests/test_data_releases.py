"""BLS's published series, FiscalData's cash, debt and auctions, the CFTC's Commitments of Traders and
the Fed's calendar (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.releases import (AUCTIONS_URL, BLS_SERIES, BLS_V1_URL, COT_MARKETS, COT_URL, DEBT_URL, DTS_CASH_URL, FED_CALENDAR_URL,
                                Releases, bls_summary, parse_auctions, parse_bls, parse_calendar, parse_cot, parse_debt, parse_tga)
from ltcm.tests.fakes import Clock, FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bls():
    """api.bls.gov/publicAPI/v1/timeseries/data/ for the seven series, 2025-2026, recorded Sept 25, 2026 06:55Z."""
    return load("bls_v1_timeseries.json")


def tga():
    """FiscalData's operating cash balance, the 12 newest rows, recorded Sept 25, 2026 06:56Z."""
    return load("fiscaldata_dts_operating_cash_balance.json")


def debt():
    """FiscalData's Debt to the Penny, the 5 newest days, recorded Sept 25, 2026 06:56Z."""
    return load("fiscaldata_debt_to_penny.json")


def auctions():
    """FiscalData's auctions_query, three announced auctions and four with results, recorded Sept 25, 2026 06:57Z."""
    return load("fiscaldata_auctions_query.json")


def cot():
    """publicreporting.cftc.gov/resource/6dca-aqww.json for the six markets, the two newest reports, recorded Sept 25, 2026 06:59Z."""
    return load("cftc_legacy_futures_six_markets.json")


def calendar() -> bytes:
    """www.federalreserve.gov/json/calendar.json, recorded Sept 25, 2026 06:59Z: its FOMC, testimony and Beige Book events from
    September 2026 on, six speeches, three past FOMC events and one malformed row (the file's byte-order mark kept)."""
    return (FIXTURES / "fed_calendar.json").read_bytes()


class Bls(unittest.TestCase):
    def test_the_recorded_answer_newest_first(self):
        found = parse_bls(bls())
        self.assertEqual(sorted(found), sorted(BLS_SERIES.values()))
        cpi = found["CUSR0000SA0"]
        self.assertEqual((cpi[0]["period"], cpi[0]["value"], cpi[0]["latest"], cpi[0]["preliminary"]), ("2026-08", 334.131, True, False))
        self.assertTrue(found["CES0000000001"][0]["preliminary"])
        self.assertEqual([r["period"] for r in cpi], sorted((r["period"] for r in cpi), reverse=True))

    def test_the_summary_changes_and_a_refused_query(self):
        found = parse_bls(bls())
        summary = bls_summary("CUUR0000SA0", found["CUUR0000SA0"])
        self.assertEqual(summary["latest"]["period"], "2026-08")
        by = {r["period"]: r["value"] for r in found["CUUR0000SA0"]}
        self.assertEqual(summary["change_12m_pct"], round((by["2026-08"] / by["2025-08"] - 1) * 100, 4))
        self.assertEqual(summary["change_1m_pct"], round((by["2026-08"] / by["2026-07"] - 1) * 100, 4))
        self.assertEqual(len(summary["recent"]), 13)
        payrolls = bls_summary("CES0000000001", found["CES0000000001"])
        self.assertEqual(payrolls["diff_1m"], round(payrolls["recent"][0]["value"] - payrolls["recent"][1]["value"], 4))
        with self.assertRaises(DataError) as refused:
            parse_bls({"status": "REQUEST_NOT_PROCESSED", "message": ["Request could not be serviced, as the daily threshold for total "
                                                                      "number of requests allocated to the user has been reached."]})
        self.assertIn("daily threshold", str(refused.exception))
        with self.assertRaises(DataError):
            bls_summary("X", [])

    def test_one_post_for_every_series_with_the_contact_user_agent(self):
        transport = FakeTransport({("POST", BLS_V1_URL): bls()})
        Releases(transport, clock=Clock("2026-09-25T07:00:00Z")).bls(list(BLS_SERIES.values()))
        call = transport.calls[0]
        self.assertEqual((call["method"], call["headers"]["User-Agent"]), ("POST", CONTACT_USER_AGENT))
        self.assertEqual(call["body"], {"seriesid": list(BLS_SERIES.values()), "startyear": "2025", "endyear": "2026"})


class Fiscal(unittest.TestCase):
    def test_the_treasury_general_account(self):
        found = parse_tga(tga())
        self.assertEqual((found["record_date"], found["closing"], found["opening"], found["units"]),
                         ("2026-09-23", 947317.0, 957409.0, "millions of dollars"))
        self.assertEqual(found["days"][0], {"date": "2026-09-23", "closing": 947317.0})

    def test_debt_to_the_penny(self):
        found = parse_debt(debt())
        self.assertEqual((found["record_date"], found["total"]), ("2026-09-23", 40073558531201.68))
        self.assertEqual(found["change_1d"], round(40073558531201.68 - 40097834028442.07, 2))

    def test_auctions_announced_and_with_results(self):
        found = parse_auctions(auctions())
        self.assertEqual([a["term"] for a in found["upcoming"]], ["26-Week", "52-Week", "6-Week"])
        seven = [a for a in found["recent"] if a["term"] == "7-Year"][0]
        self.assertEqual((seven["auction_date"], seven["high_yield"], seven["bid_to_cover"], seven["offering_bn"]), ("2026-09-24", 5.085, 2.42, 44.0))
        self.assertAlmostEqual(seven["indirect_pct"], round(24869544500 / 50624250500 * 100, 2))
        bill = [a for a in found["recent"] if a["term"] == "8-Week"][0]
        self.assertEqual((bill["high_yield"], bill["high_discount_rate"], bill["high_investment_rate"]), (None, 3.99, 4.071))

    def test_the_requests(self):
        transport = FakeTransport({DTS_CASH_URL: tga(), DEBT_URL: debt(), AUCTIONS_URL: auctions()})
        client = Releases(transport)
        client.tga(), client.debt(), client.auctions()
        self.assertEqual([c["query"].get("sort") for c in transport.calls], ["-record_date", "-record_date", "-auction_date"])


class Cot(unittest.TestCase):
    def test_the_recorded_reports_oldest_first(self):
        rows = parse_cot(cot())
        self.assertEqual(len(rows), 12)
        self.assertEqual([r["as_of"] for r in rows][:1] + [r["as_of"] for r in rows][-1:], ["2026-09-08", "2026-09-15"])
        btc = [r for r in rows if r["code"] == COT_MARKETS["BTC"]][-1]
        self.assertEqual((btc["as_of"], btc["open_interest"], btc["noncommercial"]["long"], btc["noncommercial"]["short"]),
                         ("2026-09-15", 20773.0, 16744.0, 14276.0))
        self.assertEqual(btc["noncommercial"]["net"], 16744.0 - 14276.0)
        self.assertIsNotNone(btc["noncommercial"]["spread"])
        with self.assertRaises(DataError):
            parse_cot({"error": True})

    def test_a_query_for_one_market_and_a_span(self):
        transport = FakeTransport({COT_URL: cot()})
        Releases(transport).cot("133741", since="2026-07-01", before="2026-09-15", limit=30)
        query = transport.calls[0]["query"]
        self.assertEqual(query["$where"], "cftc_contract_market_code='133741' AND report_date_as_yyyy_mm_dd >= '2026-07-01' AND "
                                          "report_date_as_yyyy_mm_dd < '2026-09-15'")
        self.assertEqual((query["$order"], query["$limit"]), ("report_date_as_yyyy_mm_dd DESC", "30"))


class Calendar(unittest.TestCase):
    def test_the_recorded_calendar_by_kind_from_today(self):
        found = parse_calendar(calendar(), today="2026-09-25")
        self.assertEqual(sorted(found), ["beige", "fomc", "speeches", "testimony"])
        titles = [(e["date"], e["title"]) for e in found["fomc"]]
        self.assertEqual(titles[:3], [("2026-10-07", "FOMC Minutes"), ("2026-10-28", "FOMC Meeting"), ("2026-10-28", "FOMC Press Conference")])
        self.assertTrue(all(e["end_date"] >= "2026-09-25" for rows in found.values() for e in rows))
        meeting = [e for e in found["fomc"] if e["title"] == "FOMC Meeting"][0]
        self.assertEqual((meeting["time"], meeting["description"]), ("2:00 p.m.", "Two-day meeting, October 27 - 28 Press Conference"))

    def test_a_calendar_that_is_not_json_is_an_error(self):
        with self.assertRaises(DataError):
            parse_calendar(b"<html>maintenance</html>", today="2026-09-25")
        transport = FakeTransport({FED_CALENDAR_URL: (503, {}, b"down")})
        with self.assertRaises(DataError):
            Releases(transport).calendar()


if __name__ == "__main__":
    unittest.main()

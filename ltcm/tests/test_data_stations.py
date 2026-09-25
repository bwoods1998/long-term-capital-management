"""What the settlement stations recorded (Sept 25, 2026): the IEM's parse of the NWS climate reports,
the Aviation Weather Center's METARs and NCEI's daily summaries, read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from ltcm.data import CONTACT_USER_AGENT, DataError
from ltcm.data.stations import (CLI_DAY_URL, CLI_YEAR_URL, GHCND, METAR_URL, NCEI_URL, Stations, parse_cli_day, parse_cli_year,
                                parse_daily_summaries, parse_metars, product_issued)
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def cli_day():
    """mesonet.agron.iastate.edu/geojson/cli.py?dt=2026-09-24, recorded Sept 25, 2026 06:30Z (KNYC, KMDW, KDEN, KDSM of 568)."""
    return load("iem_cli_geojson_20260924.json")


def cli_year():
    """mesonet.agron.iastate.edu/json/cli.py?station=KNYC&year=2026, recorded Sept 25, 2026 06:28Z (Sept 10-24 of it)."""
    return load("iem_cli_knyc_2026.json")


def metars():
    """aviationweather.gov/api/data/metar?ids=KNYC,KMDW,KAUS&format=json&hours=3, recorded Sept 25, 2026 06:31Z."""
    return load("awc_metar_knyc_kmdw_kaus.json")


def metars_dated():
    """The same service with date=2026-09-20T00:00:00Z&hours=3 for KNYC and KMDW, recorded Sept 25, 2026."""
    return load("awc_metar_knyc_kmdw_20260920.json")


def summaries():
    """NCEI's daily summaries Sept 15-25 for Central Park, Midway and Hobby, recorded Sept 25, 2026 06:34Z."""
    return load("ncei_daily_summaries.json")


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class ClimateReports(unittest.TestCase):
    def test_a_product_id_carries_its_issue_time(self):
        self.assertEqual(product_issued("202609240617-KOKX-CDUS41-CLINYC"), epoch("2026-09-24T06:17:00Z"))
        self.assertIsNone(product_issued("KOKX-CLINYC"))
        self.assertIsNone(product_issued(None))

    def test_the_recorded_day_file(self):
        day = parse_cli_day(cli_day())
        self.assertEqual(sorted(day), ["KDEN", "KDSM", "KMDW", "KNYC"])
        nyc = day["KNYC"]
        self.assertEqual((nyc["date"], nyc["issued"], nyc["high"], nyc["low"], nyc["precip_in"], nyc["high_time"]),
                         ("2026-09-24", "2026-09-24T20:37:00Z", 66.0, 53.0, 0.0, "259 PM"))  # the afternoon's preliminary report
        self.assertEqual(day["KDEN"]["precip_in"], 0.01)

    def test_the_recorded_year_file_oldest_first_and_missing_is_none(self):
        rows = parse_cli_year(cli_year())
        self.assertEqual([r["date"] for r in rows][:2], ["2026-09-10", "2026-09-11"])
        self.assertEqual(rows[-2]["issued"], "2026-09-24T06:17:00Z")  # the 23rd's final, the next morning
        self.assertEqual((rows[-2]["high"], rows[-2]["low"]), (67.0, 55.0))
        self.assertTrue(all(r["high"] is None or isinstance(r["high"], float) for r in rows))
        with self.assertRaises(DataError):
            parse_cli_year({"error": "no"})
        self.assertEqual(parse_cli_year({"results": [{"station": "KNYC", "valid": "2026-09-01", "product": "x", "high": "M"}]}), [])

    def test_asked_with_the_contact_user_agent(self):
        transport = FakeTransport({CLI_YEAR_URL: cli_year(), CLI_DAY_URL: cli_day()})
        stations = Stations(transport)
        self.assertEqual(len(stations.cli_year("KNYC", 2026)), 15)
        self.assertIn("KNYC", stations.cli_day("2026-09-24"))
        self.assertEqual([c["query"] for c in transport.calls], [{"station": "KNYC", "year": "2026"}, {"dt": "2026-09-24"}])
        self.assertEqual(transport.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)


class Metars(unittest.TestCase):
    def test_the_recorded_answer_in_fahrenheit_by_receipt(self):
        rows = parse_metars(metars())
        self.assertEqual(len(rows), 9)
        self.assertEqual([r["received"] for r in rows], sorted(r["received"] for r in rows))
        austin = [r for r in rows if r["station"] == "KAUS"][-1]
        self.assertEqual((austin["received"], austin["observed"], austin["temp_f"], austin["max_6h_f"], austin["max_24h_f"]),
                         ("2026-09-25T05:56:22Z", "2026-09-25T05:53:00Z", 82.9, 93.9, 98.1))
        self.assertEqual(austin["received_at"], epoch("2026-09-25T05:56:22.934Z"))
        self.assertTrue(austin["raw"].startswith("METAR KAUS 250553Z"))
        with self.assertRaises(DataError):
            parse_metars({"status": "error"})

    def test_a_page_back_asks_for_the_hours_before_its_end(self):
        transport = FakeTransport({METAR_URL: metars_dated()})
        rows = Stations(transport).metars(["KNYC", "KMDW"], hours=3, end=epoch("2026-09-20T00:00:00Z"))
        self.assertEqual(transport.calls[0]["query"], {"ids": "KNYC,KMDW", "format": "json", "hours": "3", "date": "2026-09-20T00:00:00Z"})
        self.assertEqual(len(rows), 6)
        self.assertLess(max(r["received_at"] for r in rows), epoch("2026-09-20T00:00:00Z"))


class Summaries(unittest.TestCase):
    def test_the_recorded_answer_by_station(self):
        found = parse_daily_summaries(summaries())
        self.assertEqual(sorted(found), [GHCND["KHOU"], GHCND["KMDW"], GHCND["KNYC"]])
        nyc = found[GHCND["KNYC"]]
        self.assertEqual(nyc[-1]["date"], "2026-09-22")  # three days behind
        self.assertEqual(nyc[0], {"date": "2026-09-15", "high": nyc[0]["high"], "low": nyc[0]["low"], "precip_in": nyc[0]["precip_in"],
                                  "snow_in": nyc[0]["snow_in"]})
        self.assertIsInstance(nyc[0]["high"], float)

    def test_asked_for_every_station_at_once(self):
        transport = FakeTransport({NCEI_URL: summaries()})
        Stations(transport).daily_summaries([GHCND["KNYC"], GHCND["KMDW"]], "2026-09-11", "2026-09-25")
        query = transport.calls[0]["query"]
        self.assertEqual((query["stations"], query["dataTypes"], query["units"]), ("USW00094728,USW00014819", "TMAX,TMIN,PRCP,SNOW", "standard"))


if __name__ == "__main__":
    unittest.main()

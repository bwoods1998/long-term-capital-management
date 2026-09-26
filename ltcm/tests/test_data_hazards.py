"""The NHC's active storms and the USGS earthquake feed (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.hazards import NHC_URL, USGS_FEED_URL, Hazards, parse_quakes, parse_storms
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def storms():
    """www.nhc.noaa.gov/CurrentStorms.json, recorded Sept 25, 2026 06:59Z (five storms; the GIS product links left out)."""
    return json.loads((FIXTURES / "nhc_current_storms.json").read_text(encoding="utf-8"))


def quakes():
    """earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson, recorded Sept 25, 2026 06:59Z (12 events)."""
    return json.loads((FIXTURES / "usgs_4.5_day.geojson").read_text(encoding="utf-8"))


class Storms(unittest.TestCase):
    def test_the_recorded_storms(self):
        rows = parse_storms(storms())
        self.assertEqual([r["name"] for r in rows], ["Fay", "Gonzalo", "Nolo", "Odalys", "Polo"])
        fay = rows[0]
        self.assertEqual((fay["basin"], fay["classification"], fay["intensity_kt"], fay["pressure_mb"], fay["lat"], fay["lon"], fay["advisory"]),
                         ("atlantic", "TS", 45.0, 1005.0, 29.8, -42.3, "020"))
        self.assertEqual({r["name"]: r["basin"] for r in rows}["Nolo"], "central_pacific")  # its NHC bin is CP2

    def test_no_storm_is_an_answer_and_a_changed_shape_an_error(self):
        self.assertEqual(parse_storms({"activeStorms": []}), [])
        with self.assertRaises(DataError):
            parse_storms({"storms": []})


class Quakes(unittest.TestCase):
    def test_the_recorded_feed_newest_first(self):
        feed = parse_quakes(quakes())
        self.assertEqual((feed["count"], feed["title"]), (12, "USGS Magnitude 4.5+ Earthquakes, Past Day"))
        first = [e for e in feed["events"] if e["id"] == "us6000txim"][0]
        self.assertEqual((first["mag"], first["status"], first["origin"], first["depth_km"]), (5.0, "reviewed", "2026-09-25T04:27:40Z", 10.0))
        self.assertEqual([e["origin"] for e in feed["events"]], sorted((e["origin"] for e in feed["events"]), reverse=True))

    def test_only_the_summary_feeds_are_asked(self):
        transport = FakeTransport({NHC_URL: storms(), USGS_FEED_URL.format(feed="4.5_day"): quakes()})
        hazards = Hazards(transport)
        self.assertEqual(len(hazards.storms()), 5)
        self.assertEqual(hazards.quakes("4.5_day")["count"], 12)
        with self.assertRaises(DataError):
            hazards.quakes("../all_month")


if __name__ == "__main__":
    unittest.main()

"""Open-Meteo: ensemble member daily highs, the deterministic daily forecast, bracket odds."""

from __future__ import annotations

import unittest

from ltcm.data import DataError
from ltcm.data.openmeteo import (
    ENSEMBLE_HOST,
    FORECAST_HOST,
    USER_AGENT,
    OpenMeteo,
    bracket_probability,
    daily_highs,
    summarize,
)
from ltcm.tests.fakes import Clock, FakeTransport

ENSEMBLE = ENSEMBLE_HOST + "/v1/ensemble?*"
FORECAST = FORECAST_HOST + "/v1/forecast?*"


def hours(day, values):
    return [f"2026-09-{day:02d}T{h:02d}:00" for h in range(len(values))]


def ensemble_json(multi_model=True):
    """Two local days of hourly members; day one peaks at hour 15, day two runs cooler."""
    time = hours(18, range(24)) + hours(19, range(24))

    def path(peak_day1, peak_day2):
        out = []
        for h in range(24):
            out.append(peak_day1 - abs(15 - h) * 1.5)
        for h in range(24):
            out.append(peak_day2 - abs(14 - h) * 1.5)
        return out

    if multi_model:
        hourly = {
            "time": time,
            "temperature_2m_ncep_gefs_seamless": path(82.0, 70.0),
            "temperature_2m_member01_ncep_gefs_seamless": path(84.0, 71.0),
            "temperature_2m_member02_ncep_gefs_seamless": path(80.0, 69.0),
            "temperature_2m_ecmwf_ifs025_ensemble": path(83.0, 72.0),
            "temperature_2m_member01_ecmwf_ifs025_ensemble": path(81.0, 73.0),
        }
        # One member has a null at its peak hour: the next-highest hour counts instead.
        hourly["temperature_2m_member01_ecmwf_ifs025_ensemble"][15] = None
    else:
        hourly = {
            "time": time,
            "temperature_2m": path(82.0, 70.0),
            "temperature_2m_member01": path(84.0, 71.0),
            "temperature_2m_member02": path(80.0, 69.0),
        }
    return {
        "latitude": 40.75,
        "longitude": -74.0,
        "generationtime_ms": 0.78,
        "utc_offset_seconds": -14400,
        "timezone": "America/New_York",
        "timezone_abbreviation": "GMT-4",
        "elevation": 44.0,
        "hourly_units": {"time": "iso8601", "temperature_2m": "°F"},
        "hourly": hourly,
    }


FORECAST_JSON = {
    "latitude": 40.78858,
    "longitude": -73.9661,
    "timezone": "America/New_York",
    "daily_units": {"time": "iso8601", "temperature_2m_max": "°F", "temperature_2m_min": "°F"},
    "daily": {"time": ["2026-09-18", "2026-09-19", "2026-09-20"], "temperature_2m_max": [81.8, 67.2, None], "temperature_2m_min": [66.6, 55.9, 63.5]},
}


class OpenMeteoCase(unittest.TestCase):
    def transport(self, **overrides):
        routes = {ENSEMBLE: ensemble_json(), FORECAST: FORECAST_JSON}
        routes.update(overrides)
        return FakeTransport(routes)

    def source(self, transport=None):
        return OpenMeteo(transport or self.transport(), clock=Clock("2026-09-18T06:30:00Z"))


class EnsembleTests(OpenMeteoCase):
    def test_member_paths_reduce_to_daily_highs_with_a_distribution(self):
        transport = self.transport()
        answer = self.source(transport).ensemble_daily_high(40.7789, -73.9692, days=2)
        self.assertEqual(answer["timezone"], "America/New_York")
        self.assertEqual(answer["models"], ["gfs_seamless", "ecmwf_ifs025"])
        self.assertEqual(answer["unit"], "F")
        self.assertEqual(answer["fetched_at"], "2026-09-18T06:30:00Z")
        self.assertEqual([d["date"] for d in answer["days"]], ["2026-09-18", "2026-09-19"])
        first = answer["days"][0]
        # The null at member01_ecmwf's peak hour drops that member's high to its 79.5 shoulder.
        self.assertEqual(first["members"], [79.5, 80.0, 82.0, 83.0, 84.0])
        self.assertEqual(first["n"], 5)
        self.assertEqual(first["mean"], 81.7)
        self.assertEqual(first["p50"], 82.0)
        self.assertEqual(first["p10"], 79.7)
        self.assertEqual(first["p90"], 83.6)
        self.assertEqual((first["min"], first["max"]), (79.5, 84.0))
        self.assertEqual(first["sd"], 1.92)
        self.assertEqual(answer["days"][1]["members"], [69.0, 70.0, 71.0, 72.0, 73.0])
        query = transport.last["query"]
        self.assertEqual(query["hourly"], "temperature_2m")
        self.assertEqual(query["models"], "gfs_seamless,ecmwf_ifs025")
        self.assertEqual(query["temperature_unit"], "fahrenheit")
        self.assertEqual(query["timezone"], "America/New_York")
        self.assertEqual(query["forecast_days"], "2")
        self.assertEqual(transport.last["headers"]["User-Agent"], USER_AGENT)

    def test_a_single_model_answer_uses_the_bare_member_names(self):
        answer = self.source(self.transport(**{ENSEMBLE: ensemble_json(multi_model=False)})).ensemble_daily_high(40.7789, -73.9692, days=1, models="gfs_seamless")
        self.assertEqual(len(answer["days"]), 1)
        self.assertEqual(answer["days"][0]["members"], [80.0, 82.0, 84.0])
        self.assertEqual(answer["models"], ["gfs_seamless"])

    def test_failures_are_data_errors(self):
        with self.assertRaises(DataError):
            self.source(self.transport(**{ENSEMBLE: {"error": True, "reason": "Cannot initialize MultiDomains from invalid String value bogus"}})).ensemble_daily_high(1, 2)
        with self.assertRaises(DataError):
            self.source(self.transport(**{ENSEMBLE: {"hourly": {"time": []}}})).ensemble_daily_high(1, 2)
        with self.assertRaises(DataError):
            self.source(self.transport(**{ENSEMBLE: (503, {}, b"down")})).ensemble_daily_high(1, 2)
        with self.assertRaises(DataError):
            self.source(self.transport(**{ENSEMBLE: {"hourly": {"time": ["2026-09-18T00:00"], "temperature_2m": [None]}}})).ensemble_daily_high(1, 2)

    def test_daily_highs_and_summarize_are_defensive(self):
        rows = daily_highs({"time": ["2026-09-18T00:00", "2026-09-18T01:00", "2026-09-19T00:00"], "temperature_2m": [70, "71.5", "x"], "temperature_2m_member01": "junk"})
        self.assertEqual([(r["date"], r["members"], r["n"]) for r in rows], [("2026-09-18", [71.5], 1), ("2026-09-19", [], 0)])
        self.assertEqual(summarize([])["mean"], None)
        self.assertEqual(summarize([80.0])["sd"], 0.0)


class ForecastTests(OpenMeteoCase):
    def test_the_daily_forecast_is_highs_and_lows(self):
        transport = self.transport()
        answer = self.source(transport).forecast_daily(40.7789, -73.9692, days=3)
        self.assertEqual(answer["days"], [
            {"date": "2026-09-18", "high": 81.8, "low": 66.6},
            {"date": "2026-09-19", "high": 67.2, "low": 55.9},
            {"date": "2026-09-20", "high": None, "low": 63.5},
        ])
        self.assertEqual(transport.last["query"]["daily"], "temperature_2m_max,temperature_2m_min")
        self.assertEqual(transport.last["query"]["forecast_days"], "3")
        with self.assertRaises(DataError):
            self.source(self.transport(**{FORECAST: {"daily": {}}})).forecast_daily(1, 2)


class BracketTests(unittest.TestCase):
    def test_the_bracket_counts_rounded_highs_inclusively_with_a_small_prior(self):
        members = [79.4, 79.5, 80.2, 81.9, 82.0, 83.7]  # rounds to 79, 80, 80, 82, 82, 84
        self.assertAlmostEqual(bracket_probability(members, 80, 82, smoothing=0), 4 / 6)
        self.assertAlmostEqual(bracket_probability(members, 80, 82), 4.5 / 7)
        self.assertAlmostEqual(bracket_probability(members, None, 79, smoothing=0), 1 / 6)
        self.assertAlmostEqual(bracket_probability(members, 84, None, smoothing=0), 1 / 6)
        self.assertAlmostEqual(bracket_probability(members, 90, 95), 0.5 / 7, "no member reached it, yet not zero")
        self.assertEqual(bracket_probability([], 80, 82), 0.5)
        self.assertEqual(bracket_probability([], 80, 82, smoothing=0), 0.0)
        self.assertAlmostEqual(OpenMeteo.bracket_probability(["80", None, "bad", 81], 80, 81, smoothing=0), 1.0)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- recorded payloads, Sept 24, 2026
import copy  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from ltcm.data import iso  # noqa: E402
from ltcm.data.openmeteo import (  # noqa: E402
    HISTORICAL_HOST,
    climate_day,
    ensemble_climate_days,
    member_series,
    previous_run_days,
)

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def fixture(name):
    """A payload recorded from the live host on Sept 24, 2026 (trimmed; see the file's first keys)."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ClimateDays(unittest.TestCase):
    """The House's weather recorders aggregate by the NWS climate day: the CLI report -- and every
    Kalshi high, low and rain market -- settles on midnight-to-midnight local STANDARD time."""

    def test_a_climate_day_is_local_standard_time_all_year(self):
        self.assertEqual(climate_day("2026-09-24T04:00", -5), "2026-09-23")  # 00:00 EDT is still Sept 23 in the record
        self.assertEqual(climate_day("2026-09-24T05:00", -5), "2026-09-24")
        self.assertEqual(climate_day("2026-01-15T05:00Z", -5), "2026-01-15")
        self.assertEqual(climate_day("2026-09-24T07:59", -8), "2026-09-23")

    def test_recorded_ensemble_members_by_climate_day(self):
        payload = fixture("openmeteo_ensemble_knyc.json")
        members = member_series(payload["hourly"], "temperature_2m")
        self.assertEqual(sorted(members), ["control/ecmwf_ifs025_ensemble", "control/ncep_gefs_seamless",
                                           "member01/ecmwf_ifs025_ensemble", "member01/ncep_gefs_seamless",
                                           "member02/ecmwf_ifs025_ensemble", "member02/ncep_gefs_seamless"])
        rows = ensemble_climate_days(payload["hourly"], -5)
        # The answer runs 00:00Z Sept 24 to 23:00Z Sept 27: Sept 23's climate day and Sept 27's are not whole.
        self.assertEqual([row["date"] for row in rows], ["2026-09-24", "2026-09-25", "2026-09-26"])
        hourly = payload["hourly"]
        hours = [i for i, stamp in enumerate(hourly["time"]) if climate_day(stamp, -5) == "2026-09-25"]
        self.assertEqual(len(hours), 24)
        series = hourly["temperature_2m_member01_ncep_gefs_seamless"]
        self.assertIn(round(max(series[i] for i in hours), 1), rows[1]["high"]["members"])
        self.assertIn(round(min(series[i] for i in hours), 1), rows[1]["low"]["members"])
        rain = hourly["precipitation_member01_ecmwf_ifs025_ensemble"]
        self.assertIn(round(sum(rain[i] for i in hours), 3), rows[1]["precip_in"]["members"])
        self.assertEqual([row["high"]["n"] for row in rows], [6, 6, 6])
        self.assertLessEqual(rows[1]["low"]["max"], rows[1]["high"]["min"] + 30)
        json.dumps(rows, allow_nan=False)  # it ships as JSON

    def test_a_member_missing_an_hour_is_left_out_of_that_day_never_filled(self):
        hourly = copy.deepcopy(fixture("openmeteo_ensemble_knyc.json")["hourly"])
        first_of_25 = next(i for i, stamp in enumerate(hourly["time"]) if climate_day(stamp, -5) == "2026-09-25")
        hourly["temperature_2m_member01_ncep_gefs_seamless"][first_of_25 + 3] = None
        rows = ensemble_climate_days(hourly, -5)
        self.assertEqual([row["high"]["n"] for row in rows], [6, 5, 6])
        self.assertEqual(ensemble_climate_days({"time": hourly["time"][:20], "temperature_2m": [50.0] * 20}, -5), [])

    def test_recorded_previous_runs_by_lead_and_model(self):
        payload = fixture("openmeteo_previous_runs_knyc.json")
        days = previous_run_days(payload["hourly"], -5, ["gfs_seamless", "ecmwf_ifs025"])
        # UTC Sept 1-3 cover the climate days of Sept 1 and 2 whole (Sept 3's runs to 04:00Z Sept 4).
        self.assertEqual(sorted(days), ["2026-09-01", "2026-09-02"])
        self.assertEqual(sorted(days["2026-09-01"]), [1, 2, 3])
        hourly = payload["hourly"]
        hours = [i for i, stamp in enumerate(hourly["time"]) if climate_day(stamp, -5) == "2026-09-01"]
        values = [hourly["temperature_2m_previous_day2_ecmwf_ifs025"][i] for i in hours]
        self.assertEqual(days["2026-09-01"][2]["ecmwf_ifs025"]["high"], round(max(values), 1))
        self.assertEqual(days["2026-09-01"][2]["ecmwf_ifs025"]["low"], round(min(values), 1))
        rain = [hourly["precipitation_previous_day1_gfs_seamless"][i] for i in hours]
        self.assertEqual(days["2026-09-01"][1]["gfs_seamless"]["precip_in"], round(sum(rain), 3))
        # A model with an hour missing at a lead has no entry for that day and lead; the others stand.
        broken = copy.deepcopy(hourly)
        broken["temperature_2m_previous_day3_gfs_seamless"][hours[5]] = None
        again = previous_run_days(broken, -5, ["gfs_seamless", "ecmwf_ifs025"])
        self.assertEqual(sorted(again["2026-09-01"][3]), ["ecmwf_ifs025"])
        self.assertEqual(sorted(again["2026-09-01"][1]), ["ecmwf_ifs025", "gfs_seamless"])

    def test_run_times_come_from_meta_json_and_a_file_without_them_is_an_error(self):
        meta = ENSEMBLE_HOST + "/data/ncep_gefs025/static/meta.json"
        transport = FakeTransport({meta: fixture("openmeteo_meta_ncep_gefs025.json"),
                                   ENSEMBLE_HOST + "/data/bad/static/meta.json": {"chunk_time_length": 1}})
        client = OpenMeteo(transport, clock=Clock("2026-09-24T03:30:00Z"))
        self.assertEqual(client.run("ncep_gefs025"), {"model": "ncep_gefs025", "init": iso(1790186400),
                                                      "available": iso(1790206939), "modified": iso(1790206939)})
        self.assertEqual(transport.last["headers"]["User-Agent"], USER_AGENT)
        with self.assertRaises(DataError):
            client.run("bad")

    def test_the_ensemble_and_the_archive_are_asked_in_utc_with_both_models(self):
        transport = FakeTransport({ENSEMBLE: fixture("openmeteo_ensemble_knyc.json"),
                                   HISTORICAL_HOST + "/v1/forecast?*": fixture("openmeteo_previous_runs_knyc.json")})
        client = OpenMeteo(transport, clock=Clock("2026-09-24T03:30:00Z"))
        days = client.ensemble_days(40.7789, -73.9692, -5)
        query = transport.calls[-1]["query"]
        self.assertEqual((query["timezone"], query["models"], query["hourly"], query["precipitation_unit"]),
                         ("GMT", "gfs_seamless,ecmwf_ifs025", "temperature_2m,precipitation", "inch"))
        self.assertEqual([row["date"] for row in days["days"]], ["2026-09-24", "2026-09-25", "2026-09-26"])
        archive = client.previous_runs(40.7789, -73.9692, "2026-09-01", "2026-09-03", -5)
        query = transport.calls[-1]["query"]
        self.assertEqual((query["start_date"], query["end_date"], query["timezone"]), ("2026-09-01", "2026-09-03", "GMT"))
        self.assertEqual(query["hourly"].split(","), [f"{v}_previous_day{n}" for v in ("temperature_2m", "precipitation") for n in (1, 2, 3)])
        self.assertNotIn("previous_day0", query["hourly"])  # day 0 is an analysis of what happened, never asked for
        self.assertEqual(sorted(archive["days"]), ["2026-09-01", "2026-09-02"])

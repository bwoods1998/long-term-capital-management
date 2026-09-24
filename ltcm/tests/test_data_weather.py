"""NWS weather: points, daily and hourly periods, the station reading, in Fahrenheit strings."""

from __future__ import annotations

import unittest
from decimal import Decimal

from ltcm.data import DataError
from ltcm.data.weather import (
    CITIES,
    OBSERVATION_URL,
    USER_AGENT,
    Weather,
    city_for,
    error_band,
    fahrenheit,
)
from ltcm.tests.fakes import Clock, FakeTransport

POINTS = "https://api.weather.gov/points/40.7789,-73.9692"
FORECAST = "https://api.weather.gov/gridpoints/OKX/33,37/forecast"
HOURLY = "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"
OBSERVATION = OBSERVATION_URL.format(station="KNYC")

POINTS_JSON = {
    "properties": {
        "gridId": "OKX",
        "gridX": 33,
        "gridY": 37,
        "forecast": FORECAST,
        "forecastHourly": HOURLY,
        "observationStations": "https://api.weather.gov/gridpoints/OKX/33,37/stations",
        "timeZone": "America/New_York",
    }
}

FORECAST_JSON = {
    "properties": {
        "periods": [
            {"number": 1, "name": "Tonight", "startTime": "2026-09-15T18:00:00-04:00", "endTime": "2026-09-16T06:00:00-04:00",
             "isDaytime": False, "temperature": 62, "temperatureUnit": "F", "shortForecast": "Clear", "detailedForecast": "Clear, with a low around 62."},
            {"number": 2, "name": "Tuesday", "startTime": "2026-09-16T06:00:00-04:00", "endTime": "2026-09-16T18:00:00-04:00",
             "isDaytime": True, "temperature": 78, "temperatureUnit": "F", "shortForecast": "Sunny", "detailedForecast": "Sunny, with a high near 78."},
            {"number": 3, "name": "Tuesday Night", "startTime": "2026-09-16T18:00:00-04:00", "endTime": "2026-09-17T06:00:00-04:00",
             "isDaytime": False, "temperature": 60, "temperatureUnit": "F", "shortForecast": "Mostly clear", "detailedForecast": "Low around 60."},
            {"number": 4, "name": "Wednesday", "startTime": "2026-09-17T06:00:00-04:00", "endTime": "2026-09-17T18:00:00-04:00",
             "isDaytime": True, "temperature": 26, "temperatureUnit": "C", "shortForecast": "Sunny", "detailedForecast": "High near 79."},
        ]
    }
}


def hourly_json(start_hour=18, count=40):
    periods = []
    day, hour = 15, start_hour
    for n in range(count):
        # A gentle diurnal curve: warmest mid-afternoon, coolest before dawn.
        temperature = 64 + (14 if 12 <= hour <= 16 else 8 if 9 <= hour <= 18 else 0) - (4 if 3 <= hour <= 6 else 0)
        periods.append({
            "number": n + 1,
            "startTime": f"2026-09-{day:02d}T{hour:02d}:00:00-04:00",
            "endTime": f"2026-09-{day:02d}T{(hour + 1) % 24:02d}:00:00-04:00",
            "isDaytime": 6 <= hour < 18,
            "temperature": temperature,
            "temperatureUnit": "F",
            "shortForecast": "Sunny" if 6 <= hour < 18 else "Clear",
        })
        hour += 1
        if hour == 24:
            hour, day = 0, day + 1
    return {"properties": {"periods": periods}}


OBSERVATION_JSON = {
    "properties": {
        "timestamp": "2026-09-15T18:51:00+00:00",
        "textDescription": "Clear",
        "temperature": {"unitCode": "wmoUnit:degC", "value": 23.3, "qualityControl": "V"},
    }
}


class WeatherCase(unittest.TestCase):
    def transport(self, **overrides):
        routes = {
            POINTS: POINTS_JSON,
            FORECAST: FORECAST_JSON,
            HOURLY: hourly_json(),
            OBSERVATION: OBSERVATION_JSON,
        }
        routes.update(overrides)
        return FakeTransport(routes)

    def weather(self, transport=None):
        return Weather(transport or self.transport(), clock=Clock("2026-09-15T22:30:00Z"))


class ForecastTests(WeatherCase):
    def test_a_city_answers_with_highs_lows_the_hourly_path_and_the_reading(self):
        transport = self.transport()
        answer = self.weather(transport).forecast("New York")
        self.assertEqual(answer["city"], "New York")
        self.assertEqual(answer["station"], "KNYC")
        self.assertTrue(answer["station_verified"])
        self.assertEqual(answer["timezone"], "America/New_York")
        self.assertEqual(answer["today"], "2026-09-15")
        days = {row["date"]: row for row in answer["days"]}
        self.assertEqual(days["2026-09-15"]["overnight_low"], "62.0")
        self.assertIsNone(days["2026-09-15"]["day_high"], "the day period had already passed")
        self.assertEqual(days["2026-09-16"]["day_high"], "78.0")
        self.assertEqual(days["2026-09-16"]["overnight_low"], "60.0")
        self.assertEqual(days["2026-09-17"]["day_high"], "78.8", "a Celsius period is converted")
        # The hourly path's calendar-day extremes are what a daily market settles on.
        self.assertEqual(days["2026-09-16"]["hourly_max"], "78.0")
        self.assertEqual(days["2026-09-16"]["hourly_min"], "60.0")
        self.assertEqual(days["2026-09-16"]["hours"], 24)
        self.assertEqual(len(answer["hourly"]), 36)
        self.assertEqual(answer["hourly"][0]["temperature"], "72.0")
        self.assertEqual(answer["observation"], {"station": "KNYC", "temperature": "73.9", "at": "2026-09-15T18:51:00Z", "description": "Clear"})
        self.assertEqual(answer["error_band_f"], "2.5")
        self.assertEqual([row["error_band_f"] for row in answer["days"]], ["2.5", "3.5", "4.5"])
        self.assertEqual(answer["as_of"], "2026-09-15T22:30:00Z")

    def test_every_request_identifies_the_floor_and_asks_for_geojson(self):
        transport = self.transport()
        self.weather(transport).forecast("nyc")
        self.assertEqual([c["url"] for c in transport.calls], [POINTS, FORECAST, HOURLY, OBSERVATION])
        for call in transport.calls:
            self.assertEqual(call["headers"]["User-Agent"], USER_AGENT)
            self.assertEqual(call["headers"]["Accept"], "application/geo+json")

    def test_the_grid_lookup_is_cached_per_process(self):
        transport = self.transport()
        weather = self.weather(transport)
        weather.forecast("New York")
        weather.forecast("New York")
        self.assertEqual(sum(1 for c in transport.calls if c["url"] == POINTS), 1)

    def test_a_missing_reading_is_none_not_an_error(self):
        answer = self.weather(self.transport(**{OBSERVATION: (503, {}, b"{}")})).forecast("New York")
        self.assertIsNone(answer["observation"])
        blank = {"properties": {"timestamp": "2026-09-15T18:51:00+00:00", "temperature": {"unitCode": "wmoUnit:degC", "value": None}}}
        self.assertIsNone(self.weather(self.transport(**{OBSERVATION: blank})).forecast("New York")["observation"])

    def test_failures_are_data_errors_with_a_short_reason(self):
        with self.assertRaises(DataError) as caught:
            self.weather().forecast("Atlantis")
        self.assertIn("unknown city", str(caught.exception))
        with self.assertRaises(DataError):
            self.weather(self.transport(**{FORECAST: (500, {}, b"down")})).forecast("New York")
        with self.assertRaises(DataError):
            self.weather(self.transport(**{POINTS: {"properties": {}}})).forecast("New York")
        with self.assertRaises(DataError):
            self.weather(self.transport(**{HOURLY: {"properties": {"periods": []}}})).forecast("New York")


class TableTests(unittest.TestCase):
    def test_the_cities_kalshi_lists_are_known_with_their_stations(self):
        for name in ("New York", "Chicago", "Miami", "Austin", "Denver", "Los Angeles", "Philadelphia", "Seattle",
                     "Atlanta", "Houston", "Dallas", "Phoenix", "Boston", "Washington DC", "Las Vegas",
                     "San Francisco", "Minneapolis", "Oklahoma City", "New Orleans", "San Antonio"):
            city = city_for(name)
            self.assertRegex(city.station, r"^K[A-Z]{3}$", name)
            self.assertTrue(-125 < city.longitude < -66 and 24 < city.latitude < 49, name)
            self.assertTrue(city.station_verified, name)
            self.assertRegex(city.series_hint, r"^KXHIGHT?[A-Z]+$", name)
        # Kalshi's newer cities carry a T: the series without it does not exist.
        self.assertEqual(city_for("Phoenix").series_hint, "KXHIGHTPHX")
        self.assertEqual(city_for("New York").series_hint, "KXHIGHNY")
        self.assertEqual(city_for("NYC").station, "KNYC")
        self.assertEqual(city_for("Washington, D.C.").station, "KDCA")
        self.assertEqual(city_for(" los angeles ").name, "Los Angeles")

    def test_temperatures_convert_and_refuse_unknown_units(self):
        self.assertEqual(fahrenheit(23.3, "wmoUnit:degC"), Decimal("73.9"))
        self.assertEqual(fahrenheit(78, "F"), Decimal("78.0"))
        self.assertEqual(fahrenheit(26, "C"), Decimal("78.8"))
        self.assertIsNone(fahrenheit(None, "F"))
        self.assertIsNone(fahrenheit("nan", "F"))
        with self.assertRaises(DataError):
            fahrenheit(20, "K")

    def test_the_error_band_widens_a_degree_a_day(self):
        self.assertEqual([str(error_band(n)) for n in range(3)], ["2.5", "3.5", "4.5"])


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- the House's recorders, Sept 24, 2026
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from ltcm.data.weather import (  # noqa: E402
    CITIES,
    city_for_series,
    city_of_station,
    standard_offset_hours,
    station_for,
)

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def recorded(name):
    """A payload recorded from api.weather.gov on Sept 24, 2026 at 03:16Z (trimmed to the fields relied on)."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SeriesAndStations(unittest.TestCase):
    def test_every_temperature_series_of_the_weather_desk_names_its_settlement_station(self):
        from league import niches

        desk = niches.load()["kalshi-weather"]
        temperature = [s for s in desk.universe if s.startswith(("KXHIGH", "KXLOWT"))]
        self.assertGreaterEqual(len(temperature), 30)
        self.assertEqual([s for s in temperature if station_for(s) is None], [])
        self.assertEqual({s: station_for(s) for s in ("KXHIGHNY", "KXLOWTNYC", "KXHIGHTPHX", "KXLOWTPHIL", "KXHIGHCHI", "KXRAINNYC")},
                         {"KXHIGHNY": "KNYC", "KXLOWTNYC": "KNYC", "KXHIGHTPHX": "KPHX", "KXLOWTPHIL": "KPHL",
                          "KXHIGHCHI": "KMDW", "KXRAINNYC": "KNYC"})
        # Nothing is guessed: a series that names no known city, and anything that is not a series.
        self.assertEqual([station_for(s) for s in ("KXRAIN", "KXRAINWKND", "KXHIGHTUL", "KXBTCD", "", None)], [None] * 6)
        self.assertEqual((station_for("KNYC"), station_for("nyc"), station_for("Los Angeles"), station_for("kmdw")),
                         ("KNYC", "KNYC", "KLAX", "KMDW"))
        self.assertIsNone(city_for_series("KXHIGHT"))

    def test_the_climate_day_offset_is_standard_time(self):
        self.assertEqual({CITIES[k].station: standard_offset_hours(CITIES[k]) for k in ("new york", "chicago", "denver", "phoenix", "los angeles")},
                         {"KNYC": -5.0, "KMDW": -6.0, "KDEN": -7.0, "KPHX": -7.0, "KLAX": -8.0})
        self.assertEqual(city_of_station("KNYC").name, "New York")


class Issued(unittest.TestCase):
    def transport(self, **over):
        routes = {POINTS: recorded("nws_points_knyc.json"),
                  "https://api.weather.gov/gridpoints/OKX/34,45/forecast": recorded("nws_forecast_knyc.json"),
                  "https://api.weather.gov/gridpoints/OKX/34,45/forecast/hourly": recorded("nws_hourly_knyc.json")}
        routes.update(over)
        return FakeTransport(routes)

    def test_the_recorded_forecast_as_issued(self):
        transport = self.transport()
        answer = Weather(transport, clock=Clock("2026-09-24T03:16:37Z")).issued(CITIES["new york"])
        self.assertEqual((answer["station"], answer["issued"], answer["unit"]), ("KNYC", "2026-09-23T21:46:15Z", "F"))
        first = answer["periods"][0]
        self.assertEqual((first["name"], first["daytime"], first["temperature"], first["pop"], first["short"]),
                         ("Tonight", False, 52.0, 0.0, "Partly Cloudy"))
        self.assertEqual(answer["periods"][1]["temperature"], 68.0)  # Thursday's high
        # The hourly path starts 23:00 EDT Sept 23 (22:00 EST): the rest of the climate day of Sept 23, then whole days.
        days = {row["date"]: row for row in answer["days"]}
        self.assertEqual(days["2026-09-23"]["hours"], 2)
        self.assertEqual(days["2026-09-24"]["hours"], 24)
        hourly = recorded("nws_hourly_knyc.json")["properties"]["periods"]
        on_24 = [p["temperature"] for p in hourly if "2026-09-24T01:00:00-04:00" <= p["startTime"] < "2026-09-25T01:00:00-04:00"]
        self.assertEqual(len(on_24), 24)
        self.assertEqual((days["2026-09-24"]["hourly_max"], days["2026-09-24"]["hourly_min"]), (float(max(on_24)), float(min(on_24))))
        for call in transport.calls:
            self.assertEqual(call["headers"]["User-Agent"], USER_AGENT)
        json.dumps(answer, allow_nan=False)

    def test_a_forecast_without_an_issue_time_is_an_error_not_a_row(self):
        broken = recorded("nws_forecast_knyc.json")
        del broken["properties"]["updateTime"]
        with self.assertRaises(DataError):
            Weather(self.transport(**{"https://api.weather.gov/gridpoints/OKX/34,45/forecast": broken})).issued(CITIES["new york"])

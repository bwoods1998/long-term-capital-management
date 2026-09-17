"""National Weather Service forecasts and observations for Kalshi's daily weather markets.

Kalshi's daily high and low temperature markets settle on the reading the National Weather
Service publishes for one named station in each city, and the NWS also publishes the point
forecast for that spot. A desk that reads both, and knows how wrong a day-ahead forecast
usually is, can price every temperature bucket the market lists; these markets resolve every
day, which makes them the fastest source of scored decisions the floor can get.

Everything here is public data from `https://api.weather.gov`, read through the same bounded
transport as the other sources. The NWS asks every client to identify itself in the
`User-Agent` header with an application name and a contact address
(https://www.weather.gov/documentation/services-web-api, "Authentication"); `USER_AGENT` does.

Endpoints and the fields relied on (https://www.weather.gov/documentation/services-web-api):

    GET /points/{lat},{lon}
        properties.forecast         -> the daily forecast URL for that grid square
        properties.forecastHourly   -> the hourly forecast URL
        properties.timeZone         -> the IANA zone of the point
    GET {properties.forecast}
        properties.periods[]: name, startTime, endTime, isDaytime, temperature,
                              temperatureUnit, shortForecast, detailedForecast
    GET {properties.forecastHourly}
        properties.periods[]: startTime, endTime, temperature, temperatureUnit, shortForecast
    GET /stations/{station}/observations/latest
        properties.timestamp, properties.temperature.value (degrees C, may be null),
        properties.temperature.unitCode, properties.textDescription

The station table below carries the settlement station where Kalshi's rules name one that
this module's author could confirm (Central Park KNYC, Midway KMDW, Miami International KMIA,
Austin-Bergstrom KAUS, Denver International KDEN, Los Angeles International KLAX). The other
stations are the city's principal NWS reporting station and are UNVERIFIED as Kalshi's
settlement source; a desk reads the market's own rules before trusting one. Which of these
cities Kalshi lists on any given day is UNVERIFIED too: the desk searches the market list and
prices what it finds. Coordinates are the station's, to the precision the NWS grid needs
(about 2.5 km), and the series hints follow Kalshi's naming pattern (`KXHIGHNY`) without a
guarantee that every city's series is spelled that way.

Temperatures come back in Fahrenheit as decimal strings. The `error_band_f` on every answer
is the rule of thumb the desk prices with: a National Weather Service day-ahead high is
typically within two to three degrees of the reading, and the band widens by about a degree
per further day (UNVERIFIED as a published statistic; it is the desk's prior, not the NWS's).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from . import DataError, HttpTransport, iso, read_json, require

HOST = "https://api.weather.gov"
POINTS_URL = HOST + "/points/{lat},{lon}"
OBSERVATION_URL = HOST + "/stations/{station}/observations/latest"
USER_AGENT = "ltcm (agent@blakewoods.us)"
ACCEPT = "application/geo+json"
SOURCE = "nws"

#: The NWS publishes no rate limit; two requests a second is polite and more than enough.
MIN_INTERVAL = 0.5
#: Hours of the hourly path returned: enough to cover today and tomorrow in any US zone.
HOURLY_HOURS = 36
#: The desk's prior for a day-ahead point forecast, in degrees F; see the module docstring.
ERROR_BAND_F = Decimal("2.5")
ERROR_BAND_STEP_F = Decimal("1.0")

ONE_PLACE = Decimal("0.1")


@dataclass(frozen=True)
class City:
    """One Kalshi weather city and the NWS station it settles on."""

    name: str
    station: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    series_hint: str
    station_verified: bool

    @property
    def key(self) -> str:
        return normalize(self.name)


def normalize(name: Any) -> str:
    return " ".join(str(name or "").lower().replace(".", "").replace(",", " ").split())


def _city(name: str, station: str, lat: str, lon: str, tz: str, hint: str, verified: bool) -> City:
    return City(name, station, Decimal(lat), Decimal(lon), tz, hint, verified)


CITIES: dict[str, City] = {
    city.key: city
    for city in (
        # Series and stations as Kalshi's own market rules name them (the CLI report code), read
        # from the open markets on Sept 16, 2026. Eight hints had been missing the "T" Kalshi
        # uses for its newer cities (KXHIGHTPHX, not KXHIGHPHX), so those cities never traded.
        _city("New York", "KNYC", "40.7789", "-73.9692", "America/New_York", "KXHIGHNY", True),
        _city("Chicago", "KMDW", "41.7861", "-87.7522", "America/Chicago", "KXHIGHCHI", True),
        _city("Miami", "KMIA", "25.7959", "-80.2870", "America/New_York", "KXHIGHMIA", True),
        # Austin settles on Austin-Bergstrom (CLIAUS, KAUS), not Camp Mabry (KATT): Camp Mabry's
        # high differed from the settled value on 42 of 68 days by up to 2F (Sept 17, 2026 study).
        _city("Austin", "KAUS", "30.1945", "-97.6699", "America/Chicago", "KXHIGHAUS", True),
        _city("Denver", "KDEN", "39.8561", "-104.6737", "America/Denver", "KXHIGHDEN", True),
        _city("Los Angeles", "KLAX", "33.9425", "-118.4081", "America/Los_Angeles", "KXHIGHLAX", True),
        _city("Philadelphia", "KPHL", "39.8721", "-75.2411", "America/New_York", "KXHIGHPHIL", True),
        _city("Seattle", "KSEA", "47.4502", "-122.3088", "America/Los_Angeles", "KXHIGHTSEA", True),
        _city("Atlanta", "KATL", "33.6367", "-84.4281", "America/New_York", "KXHIGHTATL", True),
        _city("Houston", "KHOU", "29.6375", "-95.2822", "America/Chicago", "KXHIGHTHOU", True),
        _city("Dallas", "KDFW", "32.8968", "-97.0380", "America/Chicago", "KXHIGHTDAL", True),
        _city("Phoenix", "KPHX", "33.4342", "-112.0117", "America/Phoenix", "KXHIGHTPHX", True),
        _city("Boston", "KBOS", "42.3606", "-71.0097", "America/New_York", "KXHIGHTBOS", True),
        _city("Washington DC", "KDCA", "38.8521", "-77.0377", "America/New_York", "KXHIGHTDC", True),
        _city("Las Vegas", "KLAS", "36.0800", "-115.1522", "America/Los_Angeles", "KXHIGHTLV", True),
        _city("San Francisco", "KSFO", "37.6190", "-122.3749", "America/Los_Angeles", "KXHIGHTSFO", True),
        _city("Minneapolis", "KMSP", "44.8848", "-93.2223", "America/Chicago", "KXHIGHTMIN", True),
        _city("Oklahoma City", "KOKC", "35.3931", "-97.6007", "America/Chicago", "KXHIGHTOKC", True),
        _city("New Orleans", "KMSY", "29.9934", "-90.2580", "America/Chicago", "KXHIGHTNOLA", True),
        _city("San Antonio", "KSAT", "29.5337", "-98.4698", "America/Chicago", "KXHIGHTSATX", True),
    )
}
ALIASES = {
    "nyc": "new york",
    "new york city": "new york",
    "la": "los angeles",
    "dc": "washington dc",
    "washington": "washington dc",
    "washington d c": "washington dc",
    "vegas": "las vegas",
}


def city_for(name: Any) -> City:
    """The city table entry for a name a desk typed, or `DataError("weather: unknown city")`."""
    key = normalize(name)
    key = ALIASES.get(key, key)
    city = CITIES.get(key)
    if city is None:
        known = ", ".join(c.name for c in CITIES.values())
        raise DataError(f"weather: unknown city {name!r}; the desk knows {known}")
    return city


def fahrenheit(value: Any, unit: Any) -> Decimal | None:
    """A temperature as Fahrenheit to one place, or None when the source has none."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None
    if not number.is_finite():
        return None
    code = str(unit or "").upper()
    if code.endswith("C") or code.endswith("DEGC"):
        number = number * Decimal(9) / Decimal(5) + Decimal(32)
    elif not (code.endswith("F") or code.endswith("DEGF")):
        raise DataError(f"weather: temperature unit {unit!r} is not F or C")
    return number.quantize(ONE_PLACE, rounding=ROUND_HALF_UP)


def _text(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def error_band(days_ahead: int) -> Decimal:
    """The pricing prior for a forecast `days_ahead` days out (0 is today)."""
    return ERROR_BAND_F + ERROR_BAND_STEP_F * Decimal(max(0, int(days_ahead)))


class Weather:
    """Point forecasts, the hourly path and the latest observation for one Kalshi city."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 600.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock
        self._points: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ reads
    def _get(self, url: str, what: str) -> Any:
        payload = read_json(
            self.transport,
            url,
            headers={"Accept": ACCEPT, "User-Agent": USER_AGENT},
            timeout=self.timeout,
            what=what,
        )
        require(isinstance(payload, Mapping), f"{what}: not an object")
        properties = payload.get("properties")
        require(isinstance(properties, Mapping), f"{what}: no properties")
        return properties

    def points(self, city: City) -> dict[str, Any]:
        """The grid the station sits in: forecast URLs and the zone. Cached per process."""
        cached = self._points.get(city.key)
        if cached is not None:
            return cached
        url = POINTS_URL.format(lat=format(city.latitude, "f"), lon=format(city.longitude, "f"))
        properties = self._get(url, f"weather points {city.name}")
        forecast = properties.get("forecast")
        hourly = properties.get("forecastHourly")
        require(isinstance(forecast, str) and forecast.startswith(HOST), "weather points: no forecast URL")
        require(isinstance(hourly, str) and hourly.startswith(HOST), "weather points: no hourly URL")
        found = {
            "forecast": forecast,
            "hourly": hourly,
            "timezone": _text(properties.get("timeZone")) or city.timezone,
        }
        self._points[city.key] = found
        return found

    def periods(self, url: str, what: str) -> list[dict[str, Any]]:
        properties = self._get(url, what)
        rows = properties.get("periods")
        require(isinstance(rows, list) and rows, f"{what}: no periods")
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            start = _text(row.get("startTime"))
            end = _text(row.get("endTime"))
            if start is None or end is None:
                continue
            out.append(
                {
                    "name": _text(row.get("name")),
                    "start": start,
                    "end": end,
                    "is_daytime": bool(row.get("isDaytime")),
                    "temperature": fahrenheit(row.get("temperature"), row.get("temperatureUnit") or "F"),
                    "short": _text(row.get("shortForecast")),
                    "detail": _text(row.get("detailedForecast")),
                }
            )
        require(out, f"{what}: no usable periods")
        return out

    def observation(self, city: City) -> dict[str, Any] | None:
        """The station's latest reading, or None when the station has not reported."""
        try:
            properties = self._get(OBSERVATION_URL.format(station=city.station), f"weather observation {city.station}")
        except DataError:
            return None
        reading = properties.get("temperature")
        value = reading.get("value") if isinstance(reading, Mapping) else None
        unit = reading.get("unitCode") if isinstance(reading, Mapping) else "wmoUnit:degC"
        temperature = fahrenheit(value, unit or "wmoUnit:degC")
        stamp = _text(properties.get("timestamp"))
        if temperature is None or stamp is None:
            return None
        return {
            "station": city.station,
            "temperature": str(temperature),
            "at": iso(stamp),
            "description": _text(properties.get("textDescription")),
        }

    # ------------------------------------------------------------------ the answer
    def forecast(self, name: str) -> dict[str, Any]:
        """Today's and tomorrow's highs and lows, the hourly path, the latest observation."""
        city = city_for(name)
        grid = self.points(city)
        daily = self.periods(grid["forecast"], f"weather forecast {city.name}")
        hourly = self.periods(grid["hourly"], f"weather hourly {city.name}")[:HOURLY_HOURS]
        now = datetime.fromtimestamp(float(self.clock()), tz=timezone.utc)
        today = _local_date(daily[0]["start"])
        days: dict[str, dict[str, Any]] = {}

        def day(date: str) -> dict[str, Any]:
            row = days.get(date)
            if row is None:
                row = days[date] = {
                    "date": date,
                    "day_high": None,
                    "overnight_low": None,
                    "hourly_max": None,
                    "hourly_min": None,
                    "hours": 0,
                    "day_forecast": None,
                    "night_forecast": None,
                }
            return row

        for period in daily:
            row = day(_local_date(period["start"]))
            temperature = period["temperature"]
            if period["is_daytime"]:
                row["day_high"] = None if temperature is None else str(temperature)
                row["day_forecast"] = period["short"]
            else:
                row["overnight_low"] = None if temperature is None else str(temperature)
                row["night_forecast"] = period["short"]
        for period in hourly:
            temperature = period["temperature"]
            if temperature is None:
                continue
            row = day(_local_date(period["start"]))
            row["hours"] += 1
            if row["hourly_max"] is None or temperature > Decimal(row["hourly_max"]):
                row["hourly_max"] = str(temperature)
            if row["hourly_min"] is None or temperature < Decimal(row["hourly_min"]):
                row["hourly_min"] = str(temperature)

        ordered = [days[date] for date in sorted(days)]
        for index, row in enumerate(ordered):
            row["error_band_f"] = str(error_band(index))
        return {
            "source": SOURCE,
            "city": city.name,
            "station": city.station,
            "station_verified": city.station_verified,
            "series_hint": city.series_hint,
            "timezone": grid["timezone"],
            "as_of": iso(now),
            "today": today,
            "days": ordered[:3],
            "hourly": [
                {"start": period["start"], "temperature": None if period["temperature"] is None else str(period["temperature"]), "short": period["short"]}
                for period in hourly
            ],
            "observation": self.observation(city),
            "error_band_f": str(ERROR_BAND_F),
            "note": (
                "Highs and lows are the NWS point forecast for the settlement station; hourly_max and "
                "hourly_min are the calendar-day extremes of the hourly path, which is what a daily "
                "market settles on. The error band is the desk's prior, widening a degree per day out."
            ),
        }


def _local_date(stamp: str) -> str:
    """The calendar date in the period's own offset: `2026-09-16T06:00:00-04:00` -> 2026-09-16."""
    text = str(stamp)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise DataError(f"weather: unreadable period time {stamp!r}") from exc


__all__ = [
    "ALIASES",
    "CITIES",
    "City",
    "ERROR_BAND_F",
    "HOURLY_HOURS",
    "OBSERVATION_URL",
    "POINTS_URL",
    "USER_AGENT",
    "Weather",
    "city_for",
    "error_band",
    "fahrenheit",
    "normalize",
]

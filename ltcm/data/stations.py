"""What the settlement stations actually recorded: the NWS climate reports, the hourly METARs and
NCEI's daily summaries (Sept 25, 2026, the Kalshi-scale run's recorders, league/open_feeds.py).

Every Kalshi daily high, low and rain market settles on the NWS Daily Climate Report (CLI) of one
station. The House recorded forecasts of those numbers (Open-Meteo, the NWS forecast) but never the
numbers themselves, so no weather strategy could be scored against its own settlement in replay, or
see today's high climbing hour by hour. Three key-free public-domain hosts publish them with a
moment each became known, which is what a point-in-time history needs:

    GET https://mesonet.agron.iastate.edu/json/cli.py?station=KNYC&year=2026
      results[]: station, valid (the climate day), product ("202609240617-KOKX-CDUS41-CLINYC": its
      first twelve digits are the NWS product's issue time, UTC), high, low, precip, snow,
      high_time, low_time, high_normal, low_normal, ... ("M" for missing). One row per climate day:
      the NEWEST product the Iowa Environmental Mesonet parsed for it -- the next morning's final
      report, or the afternoon's preliminary one ("valid today as of 4 PM") until the final is out.
    GET https://mesonet.agron.iastate.edu/geojson/cli.py?dt=2026-09-24
      features[].properties: the same fields for every CLI station (568 on Sept 24, 2026) for one day.
      Probed Sept 25, 2026 06:30Z: KNYC's row for Sept 24 was the 20:37Z preliminary report.
    GET https://aviationweather.gov/api/data/metar?ids=KNYC,KMDW&format=json&hours=3
      []: icaoId, receiptTime (when the Aviation Weather Center received it), obsTime (unix s),
      reportTime, temp / dewp (C), wdir, wspd, wgst, visib, altim, slp, maxT / minT (the 6-hour
      extremes, C, when the report carries them), maxT24 / minT24 (the 24-hour ones), precip,
      pcp3hr, pcp6hr, pcp24hr (inches), metarType, rawOb. `date=<ISO end>` pages back; the service
      answers "Data is available for up to 30 days for date" beyond that (probed Sept 25, 2026).
    GET https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=USW00094728,...
        &startDate=..&endDate=..&dataTypes=TMAX,TMIN,PRCP,SNOW&units=standard&format=json
      []: DATE, STATION, TMAX, TMIN, PRCP, SNOW (strings, F and inches); GHCN-Daily, about three days
      behind (Sept 25, 2026: through Sept 22) and revised as the quality checks run.

Terms (read Sept 25, 2026): the IEM's data "may be used freely by anyone for any lawful purpose",
commercial use included (https://mesonet.agron.iastate.edu/disclaimer.php); the Aviation Weather
Center's Data API is key-free and asks for a custom User-Agent and at most 100 requests a minute
(https://aviationweather.gov/data/api/); NCEI's data "are in the public domain in the United States"
and its Access Data Service needs no token (https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation).
"""

from __future__ import annotations

import math
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

IEM_HOST = "https://mesonet.agron.iastate.edu"
AWC_HOST = "https://aviationweather.gov"
NCEI_HOST = "https://www.ncei.noaa.gov"
CLI_YEAR_URL = IEM_HOST + "/json/cli.py"
CLI_DAY_URL = IEM_HOST + "/geojson/cli.py"
METAR_URL = AWC_HOST + "/api/data/metar"
NCEI_URL = NCEI_HOST + "/access/services/data/v1"
#: The GHCN-Daily station of each settlement station (verified against NCEI's own station names,
#: Sept 25, 2026: "NY CITY CENTRAL PARK", "CHICAGO MIDWAY AIRPORT", ...).
GHCND: dict[str, str] = {
    "KNYC": "USW00094728", "KMDW": "USW00014819", "KMIA": "USW00012839", "KAUS": "USW00013904", "KDEN": "USW00003017",
    "KLAX": "USW00023174", "KPHL": "USW00013739", "KSEA": "USW00024233", "KATL": "USW00013874", "KHOU": "USW00012918",
    "KDFW": "USW00003927", "KPHX": "USW00023183", "KBOS": "USW00014739", "KDCA": "USW00013743", "KLAS": "USW00023169",
    "KSFO": "USW00023234", "KMSP": "USW00014922", "KOKC": "USW00013967", "KMSY": "USW00012916", "KSAT": "USW00012921",
}
#: Between two requests to one of these hosts (the AWC allows 100 a minute; the IEM throttles a
#: second an address on its busiest service).
MIN_INTERVAL = 1.0


def _number(value: Any) -> float | None:
    """A reading, or None for the IEM's "M" (missing), "T" is a trace (0.0001 inches, as the NWS writes it)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().upper()
        if text == "T":
            return 0.0001
        if not text or text == "M":
            return None
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _utc(moment: float) -> str:
    return datetime.fromtimestamp(float(moment), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def product_issued(product: Any) -> float | None:
    """The issue time (UTC epoch seconds) an NWS product id carries: "202609240617-KOKX-CDUS41-CLINYC"
    -> 2026-09-24 06:17Z. None when the id does not start with twelve digits."""
    text = str(product or "")
    if len(text) < 12 or not text[:12].isdigit():
        return None
    try:
        return datetime.strptime(text[:12], "%Y%m%d%H%M").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def cli_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One climate report as the `cli` feed keeps it, or None when it has no station, day or product time."""
    station = str(raw.get("station") or "").upper()
    valid = str(raw.get("valid") or "")[:10]
    issued = product_issued(raw.get("product"))
    if not station or len(valid) != 10 or issued is None:
        return None
    return {"station": station, "date": valid, "product": str(raw.get("product")), "issued": _utc(issued),
            "high": _number(raw.get("high")), "low": _number(raw.get("low")), "precip_in": _number(raw.get("precip")),
            "snow_in": _number(raw.get("snow")), "high_time": raw.get("high_time") if raw.get("high_time") not in (None, "M") else None,
            "low_time": raw.get("low_time") if raw.get("low_time") not in (None, "M") else None,
            "high_normal": _number(raw.get("high_normal")), "low_normal": _number(raw.get("low_normal")),
            "precip_month_in": _number(raw.get("precip_month"))}


def parse_cli_year(payload: Any) -> list[dict[str, Any]]:
    """The IEM's year of climate reports for one station, oldest day first."""
    rows = payload.get("results") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), "iem cli: no results")
    out = [row for row in (cli_row(r) for r in rows if isinstance(r, Mapping)) if row is not None]
    out.sort(key=lambda row: row["date"])
    return out


def parse_cli_day(payload: Any) -> dict[str, dict[str, Any]]:
    """The IEM's reports of every CLI station for one day, by station."""
    features = payload.get("features") if isinstance(payload, Mapping) else None
    require(isinstance(features, list), "iem cli: no features")
    out: dict[str, dict[str, Any]] = {}
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, Mapping) else None
        row = cli_row(properties) if isinstance(properties, Mapping) else None
        if row is not None:
            out[row["station"]] = row
    return out


def _c_to_f(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else round(number * 9.0 / 5.0 + 32.0, 1)


def metar_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One METAR as the `metar` feed keeps it (temperatures in F, as Kalshi's markets are), or None
    when it has no station or receipt time."""
    station = str(raw.get("icaoId") or "").upper()
    received = raw.get("receiptTime")
    if not station or not received:
        return None
    try:
        at = datetime.fromisoformat(str(received).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    observed = _number(raw.get("obsTime"))
    return {"station": station, "received": _utc(at), "received_at": at,
            "observed": _utc(observed) if observed is not None else None, "type": raw.get("metarType"),
            "temp_f": _c_to_f(raw.get("temp")), "dewpoint_f": _c_to_f(raw.get("dewp")),
            "max_6h_f": _c_to_f(raw.get("maxT")), "min_6h_f": _c_to_f(raw.get("minT")),
            "max_24h_f": _c_to_f(raw.get("maxT24")), "min_24h_f": _c_to_f(raw.get("minT24")),
            "wind_dir": raw.get("wdir") if isinstance(raw.get("wdir"), (int, str)) else None,  # degrees, or "VRB"
            "wind_kt": _number(raw.get("wspd")), "gust_kt": _number(raw.get("wgst")),
            "precip_1h_in": _number(raw.get("precip")), "precip_6h_in": _number(raw.get("pcp6hr")),
            "precip_24h_in": _number(raw.get("pcp24hr")), "raw": str(raw.get("rawOb") or "")[:300]}


def parse_metars(payload: Any) -> list[dict[str, Any]]:
    """The Aviation Weather Center's answer, oldest receipt first."""
    require(isinstance(payload, list), "awc metar: not a list")
    out = [row for row in (metar_row(r) for r in payload if isinstance(r, Mapping)) if row is not None]
    out.sort(key=lambda row: (row["received_at"], row["station"]))
    return out


def parse_daily_summaries(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """NCEI's GHCN-Daily answer as {station id: [{date, high, low, precip_in, snow_in}]}, oldest first."""
    require(isinstance(payload, list), "ncei daily summaries: not a list")
    out: dict[str, list[dict[str, Any]]] = {}
    for row in payload:
        if not isinstance(row, Mapping) or not row.get("STATION") or len(str(row.get("DATE") or "")) != 10:
            continue
        out.setdefault(str(row["STATION"]), []).append({"date": str(row["DATE"]), "high": _number(row.get("TMAX")),
                                                        "low": _number(row.get("TMIN")), "precip_in": _number(row.get("PRCP")),
                                                        "snow_in": _number(row.get("SNOW"))})
    for rows in out.values():
        rows.sort(key=lambda r: r["date"])
    return out


class Stations:
    """The IEM's climate reports, the AWC's METARs and NCEI's daily summaries, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _json(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                         timeout=self.timeout, what=what)

    def cli_year(self, station: str, year: int) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"station": station, "year": int(year)})
        return parse_cli_year(self._json(f"{CLI_YEAR_URL}?{query}", f"iem cli {station} {year}"))

    def cli_day(self, day: str) -> dict[str, dict[str, Any]]:
        if len(str(day)) != 10:
            raise DataError(f"not a day: {day!r}")
        return parse_cli_day(self._json(f"{CLI_DAY_URL}?{urllib.parse.urlencode({'dt': day})}", f"iem cli {day}"))

    def metars(self, stations: Sequence[str], *, hours: int, end: float | None = None) -> list[dict[str, Any]]:
        """The METARs of `stations` received in the `hours` before `end` (None: now)."""
        params = {"ids": ",".join(stations), "format": "json", "hours": max(1, int(hours))}
        if end is not None:
            params["date"] = _utc(end)
        return parse_metars(self._json(f"{METAR_URL}?{urllib.parse.urlencode(params)}", "awc metar"))

    def daily_summaries(self, stations: Sequence[str], start: str, end: str) -> dict[str, list[dict[str, Any]]]:
        params = {"dataset": "daily-summaries", "stations": ",".join(stations), "startDate": start, "endDate": end,
                  "dataTypes": "TMAX,TMIN,PRCP,SNOW", "units": "standard", "format": "json"}
        return parse_daily_summaries(self._json(f"{NCEI_URL}?{urllib.parse.urlencode(params)}", "ncei daily summaries"))


__all__ = ["AWC_HOST", "CLI_DAY_URL", "CLI_YEAR_URL", "GHCND", "IEM_HOST", "METAR_URL", "NCEI_HOST", "NCEI_URL", "Stations",
           "cli_row", "metar_row", "parse_cli_day", "parse_cli_year", "parse_daily_summaries", "parse_metars", "product_issued"]

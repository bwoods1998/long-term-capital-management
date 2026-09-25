"""Hazards as the agencies publish them now: the National Hurricane Center's active storms and the USGS
earthquake feed (Sept 25, 2026, the Kalshi-scale run's `storms` and `quakes` recorders,
league/open_feeds.py).

Kalshi lists hurricane and earthquake markets beside its weather series; the agencies whose numbers
they use publish key-free JSON meant for programs:

    GET https://www.nhc.noaa.gov/CurrentStorms.json
      activeStorms[]: id ("al062026"), binNumber ("AT1", "EP2", "CP1"), name, classification (TD, TS,
      HU, STD, STS, PTC, ...), intensity (kt, a string), pressure (mb, a string), latitudeNumeric,
      longitudeNumeric, movementDir (deg), movementSpeed (mph), lastUpdate, publicAdvisory {advNum,
      issuance, url}, windWatchesWarnings. Probed Sept 25, 2026 06:59Z: five storms (Fay and Gonzalo in
      the Atlantic, Odalys and Polo in the eastern Pacific, Nolo in the central Pacific).
    GET https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/<feed>.geojson  (4.5_day,
        significant_week, ...)
      metadata {generated (ms), title, count}, features[]: id, properties {mag, magType, place, time
      (origin, ms), updated (ms), status (automatic|reviewed), tsunami, sig, alert, felt, url},
      geometry.coordinates [lon, lat, depth km]. "Updated every minute."

Terms (read Sept 25, 2026): NWS/NHC data are "in the public domain ... may be used without charge for
any lawful purpose" (https://www.weather.gov/disclaimer; the NHC asks that retries stay a minute or
more apart); the USGS GeoJSON feeds are "intended to be used as a programatic interface for
applications" and USGS data is U.S. public domain
(https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php). robots.txt disallows neither path.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
USGS_FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson"
#: The USGS summary feeds a key names.
USGS_FEEDS = ("4.5_day", "2.5_day", "significant_week", "4.5_week")
#: NHC bin prefixes by basin.
BASINS = {"AT": "atlantic", "EP": "east_pacific", "CP": "central_pacific"}
MIN_INTERVAL = 1.0


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso_ms(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return datetime.fromtimestamp(number / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def storm_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One active storm, or None without an id."""
    ident = str(raw.get("id") or "")
    if not ident:
        return None
    bin_number = str(raw.get("binNumber") or "")
    advisory = raw.get("publicAdvisory") if isinstance(raw.get("publicAdvisory"), Mapping) else {}
    return {"id": ident, "name": raw.get("name"), "basin": BASINS.get(bin_number[:2], "other"), "bin": bin_number or None,
            "classification": raw.get("classification"), "intensity_kt": _number(raw.get("intensity")),
            "pressure_mb": _number(raw.get("pressure")), "lat": _number(raw.get("latitudeNumeric")),
            "lon": _number(raw.get("longitudeNumeric")), "movement_dir": _number(raw.get("movementDir")),
            "movement_mph": _number(raw.get("movementSpeed")), "last_update": raw.get("lastUpdate"),
            "advisory": advisory.get("advNum"), "advisory_issued": advisory.get("issuance"),
            "watches_warnings": bool(raw.get("windWatchesWarnings"))}


def parse_storms(payload: Any) -> list[dict[str, Any]]:
    """The NHC's active storms (an empty list is an answer: no storm), sorted by id."""
    storms = payload.get("activeStorms") if isinstance(payload, Mapping) else None
    require(isinstance(storms, list), "nhc: no activeStorms")
    return sorted((row for row in (storm_row(s) for s in storms if isinstance(s, Mapping)) if row is not None), key=lambda r: r["id"])


def quake_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    properties = raw.get("properties") if isinstance(raw.get("properties"), Mapping) else None
    if properties is None or not raw.get("id"):
        return None
    coordinates = ((raw.get("geometry") or {}).get("coordinates") or [None, None, None]) + [None, None, None]
    return {"id": str(raw["id"]), "mag": _number(properties.get("mag")), "mag_type": properties.get("magType"),
            "place": properties.get("place"), "origin": _iso_ms(properties.get("time")), "updated": _iso_ms(properties.get("updated")),
            "status": properties.get("status"), "tsunami": bool(properties.get("tsunami")), "sig": _number(properties.get("sig")),
            "alert": properties.get("alert"), "felt": _number(properties.get("felt")),
            "lon": _number(coordinates[0]), "lat": _number(coordinates[1]), "depth_km": _number(coordinates[2])}


def parse_quakes(payload: Any) -> dict[str, Any]:
    """A USGS summary feed as `{generated, title, count, events: [...] newest origin first}`."""
    features = payload.get("features") if isinstance(payload, Mapping) else None
    require(isinstance(features, list), "usgs: no features")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    events = [row for row in (quake_row(f) for f in features if isinstance(f, Mapping)) if row is not None]
    events.sort(key=lambda e: e["origin"] or "", reverse=True)
    return {"generated": _iso_ms(metadata.get("generated")), "title": metadata.get("title"), "count": len(events), "events": events}


class Hazards:
    """The NHC's active storms and the USGS earthquake feeds, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 20.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _json(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                         timeout=self.timeout, what=what)

    def storms(self) -> list[dict[str, Any]]:
        return parse_storms(self._json(NHC_URL, "nhc current storms"))

    def quakes(self, feed: str) -> dict[str, Any]:
        if feed not in USGS_FEEDS:
            raise DataError(f"usgs: no such summary feed {feed!r}")
        return parse_quakes(self._json(USGS_FEED_URL.format(feed=feed), f"usgs {feed}"))


__all__ = ["BASINS", "Hazards", "NHC_URL", "USGS_FEEDS", "USGS_FEED_URL", "parse_quakes", "parse_storms", "quake_row", "storm_row"]

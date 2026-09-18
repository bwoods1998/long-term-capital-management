"""Open-Meteo ensemble and deterministic forecasts for Kalshi's daily high-temperature markets.

Kalshi's high-temperature markets settle on the daily maximum the NWS reports for one station,
and the market lists brackets of a few degrees each. A single point forecast prices one bracket
badly; an ensemble does it well: GFS runs 31 members and ECMWF IFS 51, and the spread of their
daily highs is the forecast's own uncertainty on that day. `ensemble_daily_high()` reduces the
hourly member paths to one daily high per member; `bracket_probability()` turns those into the
fraction of members that land in a bracket, which is the price the desk compares to the market.

Both hosts are keyless and public (https://open-meteo.com/en/docs/ensemble-api, non-commercial
use, under 10,000 requests a day). Fields relied on (probed live Sept 18, 2026):

    GET https://ensemble-api.open-meteo.com/v1/ensemble
        ?latitude=..&longitude=..&hourly=temperature_2m&models=gfs_seamless,ecmwf_ifs025
        &temperature_unit=fahrenheit&timezone=America/New_York&forecast_days=3
      hourly.time[]                      local ISO hours ("2026-09-18T00:00")
      hourly.temperature_2m[]            the control member (one model requested)
      hourly.temperature_2m_memberNN[]   perturbed members (one model requested)
      hourly.temperature_2m_<model>[] and hourly.temperature_2m_memberNN_<model>[]
                                         when several models are requested; the suffix is
                                         Open-Meteo's own model name (ncep_gefs_seamless,
                                         ecmwf_ifs025_ensemble), not the name in the query
      {"error": true, "reason": "..."}   on a bad request, with HTTP 400
    GET https://api.open-meteo.com/v1/forecast
        ?latitude=..&longitude=..&daily=temperature_2m_max,temperature_2m_min
        &temperature_unit=fahrenheit&timezone=..&forecast_days=3
      daily.time[], daily.temperature_2m_max[], daily.temperature_2m_min[]

Every temperature is Fahrenheit and every value in a result is a float, int, str or None so
it ships as JSON. The ensemble's grid point is the nearest model cell, a few kilometres from
the station, and the members are hourly samples, so a member's daily high slightly understates
the station's instantaneous maximum; the desk's calibration owns that bias, not this module.
"""

from __future__ import annotations

import math
import time
import urllib.parse
from typing import Any, Mapping

from . import DataError, HttpTransport, iso, read_json, require

FORECAST_HOST = "https://api.open-meteo.com"
ENSEMBLE_HOST = "https://ensemble-api.open-meteo.com"
USER_AGENT = "ltcm (agent@blakewoods.us)"
SOURCE = "open-meteo"

#: Open-Meteo asks for fewer than 10,000 calls a day; one a second is far under that.
MIN_INTERVAL = 1.0
DEFAULT_MODELS = "gfs_seamless,ecmwf_ifs025"
DEFAULT_TIMEZONE = "America/New_York"
HOURLY_FIELD = "temperature_2m"


def _float(value: Any) -> "float | None":
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation between order statistics; `sorted_values` must be non-empty."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    low = int(math.floor(position))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def summarize(members: list[float]) -> dict[str, Any]:
    """Mean, sample standard deviation and the 10/50/90 quantiles of the member highs."""
    values = sorted(v for v in (_float(m) for m in members) if v is not None)
    n = len(values)
    if n == 0:
        return {"members": [], "mean": None, "sd": None, "p10": None, "p50": None, "p90": None, "min": None, "max": None, "n": 0}
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {
        "members": values,
        "mean": round(mean, 2),
        "sd": round(math.sqrt(variance), 2),
        "p10": round(_quantile(values, 0.10), 1),
        "p50": round(_quantile(values, 0.50), 1),
        "p90": round(_quantile(values, 0.90), 1),
        "min": values[0],
        "max": values[-1],
        "n": n,
    }


def daily_highs(hourly: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Reduce an `hourly` block to per-day member highs: `[{date, members, mean, sd, ...}]`.

    Every series whose name starts with `temperature_2m` is one member (the control included),
    grouped by the local calendar date of `hourly.time`. Hours with a null reading are skipped;
    a member with no reading on a day is left out of that day."""
    times = hourly.get("time")
    require(isinstance(times, list) and times, "open-meteo ensemble: no hourly.time")
    dates = [str(stamp)[:10] for stamp in times]
    ordered_dates: list[str] = []
    for day in dates:
        if day not in ordered_dates:
            ordered_dates.append(day)
    highs: dict[str, list[float]] = {day: [] for day in ordered_dates}
    member_keys = sorted(k for k in hourly if isinstance(k, str) and k.startswith(HOURLY_FIELD))
    for key in member_keys:
        series = hourly.get(key)
        if not isinstance(series, list):
            continue
        best: dict[str, float] = {}
        for day, raw in zip(dates, series):
            value = _float(raw)
            if value is None:
                continue
            if day not in best or value > best[day]:
                best[day] = value
        for day, value in best.items():
            highs[day].append(value)
    out = []
    for day in ordered_dates:
        row = {"date": day}
        row.update(summarize(highs[day]))
        out.append(row)
    return out


def bracket_probability(members: Any, low: Any = None, high: Any = None, smoothing: float = 0.5) -> float:
    """The fraction of members whose rounded daily high falls in [low, high], inclusive.

    `None` on either side leaves that end open. Rounding is half-up to a whole degree, the way
    the NWS reports a daily maximum. A Laplace prior of `smoothing` pseudo-counts on each side
    keeps a bracket no member reached from pricing at exactly zero."""
    values = [v for v in (_float(m) for m in (members or [])) if v is not None]
    low_f, high_f = _float(low), _float(high)
    hits = 0
    for value in values:
        rounded = math.floor(value + 0.5)
        if low_f is not None and rounded < low_f:
            continue
        if high_f is not None and rounded > high_f:
            continue
        hits += 1
    a = max(0.0, float(smoothing))
    return (hits + a) / (len(values) + 2 * a) if (len(values) + 2 * a) > 0 else 0.0


class OpenMeteo:
    """Ensemble daily highs and the deterministic daily forecast for a point."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 900.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock

    def _get(self, url: str, what: str) -> Mapping[str, Any]:
        payload = read_json(
            self.transport,
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=self.timeout,
            what=what,
        )
        require(isinstance(payload, Mapping), f"{what}: not an object")
        if payload.get("error"):
            raise DataError(f"{what}: {payload.get('reason') or 'error'}")
        return payload

    def ensemble_daily_high(
        self,
        latitude: Any,
        longitude: Any,
        days: int = 3,
        models: str = DEFAULT_MODELS,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> dict[str, Any]:
        """Per-day distribution of the ensemble members' daily highs, in Fahrenheit."""
        params = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "hourly": HOURLY_FIELD,
            "models": str(models),
            "temperature_unit": "fahrenheit",
            "timezone": str(timezone),
            "forecast_days": max(1, min(int(days), 16)),
        }
        url = ENSEMBLE_HOST + "/v1/ensemble?" + urllib.parse.urlencode(params)
        payload = self._get(url, "open-meteo ensemble")
        hourly = payload.get("hourly")
        require(isinstance(hourly, Mapping), "open-meteo ensemble: no hourly block")
        rows = daily_highs(hourly)
        require(any(row["n"] for row in rows), "open-meteo ensemble: no member readings")
        return {
            "source": SOURCE,
            "latitude": _float(payload.get("latitude")),
            "longitude": _float(payload.get("longitude")),
            "timezone": str(payload.get("timezone") or timezone),
            "models": [m for m in str(models).split(",") if m],
            "unit": "F",
            "days": rows[: max(1, int(days))],
            "fetched_at": iso(float(self.clock())),
        }

    def forecast_daily(
        self, latitude: Any, longitude: Any, days: int = 3, timezone: str = DEFAULT_TIMEZONE
    ) -> dict[str, Any]:
        """The deterministic daily high and low, in Fahrenheit: `{days: [{date, high, low}]}`."""
        params = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "daily": "temperature_2m_max,temperature_2m_min",
            "temperature_unit": "fahrenheit",
            "timezone": str(timezone),
            "forecast_days": max(1, min(int(days), 16)),
        }
        url = FORECAST_HOST + "/v1/forecast?" + urllib.parse.urlencode(params)
        payload = self._get(url, "open-meteo forecast")
        daily = payload.get("daily")
        require(isinstance(daily, Mapping), "open-meteo forecast: no daily block")
        times = daily.get("time")
        require(isinstance(times, list) and times, "open-meteo forecast: no daily.time")
        highs = daily.get("temperature_2m_max") if isinstance(daily.get("temperature_2m_max"), list) else []
        lows = daily.get("temperature_2m_min") if isinstance(daily.get("temperature_2m_min"), list) else []
        rows = []
        for index, stamp in enumerate(times):
            rows.append(
                {
                    "date": str(stamp)[:10],
                    "high": _float(highs[index]) if index < len(highs) else None,
                    "low": _float(lows[index]) if index < len(lows) else None,
                }
            )
        return {
            "source": SOURCE,
            "timezone": str(payload.get("timezone") or timezone),
            "unit": "F",
            "days": rows[: max(1, int(days))],
            "fetched_at": iso(float(self.clock())),
        }

    @staticmethod
    def bracket_probability(members: Any, low: Any = None, high: Any = None, smoothing: float = 0.5) -> float:
        return bracket_probability(members, low, high, smoothing)


__all__ = [
    "DEFAULT_MODELS",
    "ENSEMBLE_HOST",
    "FORECAST_HOST",
    "OpenMeteo",
    "USER_AGENT",
    "bracket_probability",
    "daily_highs",
    "summarize",
]

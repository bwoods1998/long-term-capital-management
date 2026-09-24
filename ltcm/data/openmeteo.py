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

Sept 24, 2026 (the House's weather recorders, league/feeds.py), three more reads, probed live
that day:

    GET https://{ensemble-api,api,historical-forecast-api}.open-meteo.com/data/<run model>/static/meta.json
      last_run_initialisation_time      unix seconds: when the newest run of that model began
      last_run_availability_time        unix seconds: when Open-Meteo had it (GEFS 0.25: 5.7 h
                                        after its start; ECMWF's ensemble 12.4 h; GFS 0.13 5.6 h;
                                        ECMWF IFS 0.25 7.3 h, on the runs of Sept 23)
      (the run models behind the query names: ENSEMBLE_RUN_MODELS, FORECAST_RUN_MODELS)
    GET https://ensemble-api.open-meteo.com/v1/ensemble?...&hourly=temperature_2m,precipitation
        &models=gfs_seamless,ecmwf_ifs025&precipitation_unit=inch&timezone=GMT
      hourly.<var>_<model> (the control) and hourly.<var>_memberNN_<model>, every hour filled
      (Open-Meteo interpolates its 3-hourly ensembles to the hour)
    GET https://historical-forecast-api.open-meteo.com/v1/forecast?...&start_date=&end_date=
        &hourly=temperature_2m_previous_day1,...,precipitation_previous_day3&models=...&timezone=GMT
      hourly.<var>_previous_dayN_<model>: the value "predicted N x 24 hours before valid time"
      (https://open-meteo.com/en/docs/previous-runs-api), archived since 2024 (GFS since 2021)

`ensemble_climate_days` and `previous_run_days` aggregate by the NWS CLIMATE DAY -- midnight to
midnight local STANDARD time, all year -- because that is the day the CLI report, and so every
Kalshi high, low and rain market, settles on: in summer a calendar day of the local clock is an
hour off it. A member (or a model at a lead) counts on a day only with all 24 of its hours there;
a day the answer does not cover whole is left out, never estimated.
"""

from __future__ import annotations

import math
import re
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone as utc_zone
from typing import Any, Iterable, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, iso, read_json, require

FORECAST_HOST = "https://api.open-meteo.com"
ENSEMBLE_HOST = "https://ensemble-api.open-meteo.com"
HISTORICAL_HOST = "https://historical-forecast-api.open-meteo.com"
USER_AGENT = CONTACT_USER_AGENT  # one constant for the whole package (ltcm/data/__init__.py)
SOURCE = "open-meteo"

#: Open-Meteo asks for fewer than 10,000 calls a day; one a second is far under that.
MIN_INTERVAL = 1.0
DEFAULT_MODELS = "gfs_seamless,ecmwf_ifs025"
DEFAULT_TIMEZONE = "America/New_York"
HOURLY_FIELD = "temperature_2m"
PRECIP_FIELD = "precipitation"
#: The runs behind each model a query names, as `meta.json` names them (probed Sept 24, 2026): the
#: ensemble API's `gfs_seamless` is GEFS 0.25 (0.5 beyond ten days) and its `ecmwf_ifs025` is ECMWF's
#: ensemble; the forecast APIs' are GFS 0.13 (with HRRR) and ECMWF's IFS 0.25.
ENSEMBLE_RUN_MODELS = {"gfs_seamless": "ncep_gefs025", "ecmwf_ifs025": "ecmwf_ifs025_ensemble"}
FORECAST_RUN_MODELS = {"gfs_seamless": "ncep_gfs013", "ecmwf_ifs025": "ecmwf_ifs025"}
#: Lead days the historical-forecast API is asked for (`<var>_previous_dayN`). Day 0 is left out on
#: purpose: it is the first hours of each run, published after most of the hours it covers -- an
#: analysis of the realized weather, not a forecast of it.
LEADS = (1, 2, 3)
HOURS_A_DAY = 24
#: A variable of the ensemble block is `<var>`, `<var>_memberNN`, `<var>_<model>` or
#: `<var>_memberNN_<model>`; anything else sharing the prefix (precipitation_probability) is not it.
_MEMBER = re.compile(r"^(?:member(\d+))?_?([a-z][a-z0-9_]*)?$")


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


def climate_day(stamp: Any, offset_hours: float) -> str:
    """The NWS climate day an hour belongs to: its UTC time (`2026-09-24T04:00`, as the API answers
    with `timezone=GMT`) moved by the station's STANDARD offset from UTC (-5 for New York all year),
    as a date. 04:00Z on Sept 24 is Sept 23 in New York's climate record."""
    text = str(stamp).strip()
    moment = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    moment = moment.replace(tzinfo=utc_zone.utc) if moment.tzinfo is None else moment.astimezone(utc_zone.utc)
    return (moment + timedelta(hours=float(offset_hours))).date().isoformat()


def _climate_index(hourly: Mapping[str, Any], offset_hours: float) -> dict[str, list[int]]:
    """The hours of each COMPLETE climate day in an hourly block (all 24 there), oldest first."""
    times = hourly.get("time")
    require(isinstance(times, list) and times, "open-meteo: no hourly.time")
    days = [climate_day(stamp, offset_hours) for stamp in times]
    counts = Counter(days)
    out: dict[str, list[int]] = {}
    for index, day in enumerate(days):
        if counts[day] == HOURS_A_DAY:
            out.setdefault(day, []).append(index)
    return out


def member_series(hourly: Mapping[str, Any], variable: str) -> dict[str, list[Any]]:
    """Every series of `variable` in an ensemble block, by member: `control` or `memberNN`, with the
    model after a slash when the answer names one (`member07/ecmwf_ifs025_ensemble`)."""
    out: dict[str, list[Any]] = {}
    for key, series in hourly.items():
        if not isinstance(key, str) or not isinstance(series, list):
            continue
        if key != variable and not key.startswith(variable + "_"):
            continue
        found = _MEMBER.match(key[len(variable) + 1:] if key != variable else "")
        if found is None:
            continue
        number, model = found.group(1), found.group(2)
        if model and (model.startswith("probability") or model.startswith("previous")):
            continue  # another variable that shares the prefix
        name = f"member{int(number):02d}" if number else "control"
        out[f"{name}/{model}" if model else name] = series
    return out


def _complete(series: Any, hours: Iterable[int]) -> list[float] | None:
    """The values of `series` at `hours`, or None unless every one of them is a number."""
    if not isinstance(series, list):
        return None
    values = [_float(series[i]) if i < len(series) else None for i in hours]
    return None if any(v is None for v in values) else values  # type: ignore[return-value]


def _distribution(values: list[float], digits: int) -> dict[str, Any]:
    """`summarize`, with the members rounded to `digits` so a row stays small."""
    out = summarize(values)
    out["members"] = [round(v, digits) for v in out["members"]]
    for name in ("mean", "sd", "p10", "p50", "p90", "min", "max"):
        if out[name] is not None:
            out[name] = round(float(out[name]), digits if name != "sd" else max(digits, 2))
    return out


def ensemble_climate_days(hourly: Mapping[str, Any], offset_hours: float) -> list[dict[str, Any]]:
    """Per complete climate day: the distribution of the members' daily HIGH and LOW (Fahrenheit, the
    extremes of their 24 hourly values) and of their precipitation TOTAL (inches). A member missing
    any hour of a day is left out of that day, never filled in."""
    index = _climate_index(hourly, offset_hours)
    temperature, precipitation = member_series(hourly, HOURLY_FIELD), member_series(hourly, PRECIP_FIELD)
    out = []
    for day, hours in index.items():
        highs, lows, totals = [], [], []
        for series in temperature.values():
            values = _complete(series, hours)
            if values is not None:
                highs.append(max(values))
                lows.append(min(values))
        for series in precipitation.values():
            values = _complete(series, hours)
            if values is not None:
                totals.append(sum(values))
        if not highs:
            continue
        out.append({"date": day, "high": _distribution(highs, 1), "low": _distribution(lows, 1),
                    "precip_in": _distribution(totals, 3) if totals else None})
    return out


def previous_run_days(hourly: Mapping[str, Any], offset_hours: float, models: Iterable[str],
                      leads: Iterable[int] = LEADS) -> dict[str, dict[int, dict[str, dict[str, Any]]]]:
    """{climate day: {lead: {model: {high, low, precip_in}}}} from a historical-forecast answer:
    each model's hourly values as predicted `lead` days before each hour, over the whole climate
    day. A model with any hour of a day missing at a lead has no entry for that day and lead."""
    index = _climate_index(hourly, offset_hours)
    models = [str(m) for m in models]
    out: dict[str, dict[int, dict[str, dict[str, Any]]]] = {}
    for day, hours in index.items():
        for lead in leads:
            for model in models:
                suffix = f"_previous_day{int(lead)}" + (f"_{model}" if len(models) > 1 else "")
                temps = _complete(hourly.get(HOURLY_FIELD + suffix), hours)
                if temps is None:
                    continue
                rain = _complete(hourly.get(PRECIP_FIELD + suffix), hours)
                out.setdefault(day, {}).setdefault(int(lead), {})[model] = {
                    "high": round(max(temps), 1), "low": round(min(temps), 1),
                    "precip_in": round(sum(rain), 3) if rain is not None else None}
    return out


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

    def run(self, model: str, host: str = ENSEMBLE_HOST) -> dict[str, Any]:
        """When the newest run of `model` (a run model: `ncep_gefs025`) began and when Open-Meteo
        had it, from its `meta.json`: `{model, init, available, modified}` as ISO stamps (`modified`:
        its last change, None when not said). Raises when the file does not say both of the first,
        or says the run was available before it began."""
        payload = self._get(f"{host}/data/{urllib.parse.quote(str(model))}/static/meta.json", f"open-meteo run {model}")
        init, available = _float(payload.get("last_run_initialisation_time")), _float(payload.get("last_run_availability_time"))
        modified = _float(payload.get("last_run_modification_time"))
        require(init is not None and available is not None and init > 0 and available >= init,
                f"open-meteo run {model}: no initialisation and availability time")
        return {"model": str(model), "init": iso(init), "available": iso(available),
                "modified": iso(modified) if modified is not None and modified > 0 else None}

    def ensemble_days(self, latitude: Any, longitude: Any, offset_hours: float, *, models: str = DEFAULT_MODELS,
                      days: int = 4) -> dict[str, Any]:
        """The members' daily highs, lows and precipitation totals for every complete climate day of
        the next `days` UTC days (`ensemble_climate_days`)."""
        params = {
            "latitude": str(latitude), "longitude": str(longitude), "hourly": f"{HOURLY_FIELD},{PRECIP_FIELD}",
            "models": str(models), "temperature_unit": "fahrenheit", "precipitation_unit": "inch", "timezone": "GMT",
            "forecast_days": max(2, min(int(days), 16)),
        }
        payload = self._get(ENSEMBLE_HOST + "/v1/ensemble?" + urllib.parse.urlencode(params), "open-meteo ensemble")
        hourly = payload.get("hourly")
        require(isinstance(hourly, Mapping), "open-meteo ensemble: no hourly block")
        rows = ensemble_climate_days(hourly, offset_hours)
        require(rows, "open-meteo ensemble: no complete climate day with member readings")
        return {"latitude": _float(payload.get("latitude")), "longitude": _float(payload.get("longitude")),
                "models": [m for m in str(models).split(",") if m], "unit": "F", "precip_unit": "in", "days": rows}

    def previous_runs(self, latitude: Any, longitude: Any, start: str, end: str, offset_hours: float, *,
                      models: str = DEFAULT_MODELS, leads: Iterable[int] = LEADS) -> dict[str, Any]:
        """Each model's forecasts at `leads` days ahead, archived, for the climate days that the UTC
        dates [start, end] cover whole (`previous_run_days`)."""
        leads = [int(n) for n in leads]
        variables = [f"{field}_previous_day{n}" for field in (HOURLY_FIELD, PRECIP_FIELD) for n in leads]
        params = {
            "latitude": str(latitude), "longitude": str(longitude), "hourly": ",".join(variables), "models": str(models),
            "temperature_unit": "fahrenheit", "precipitation_unit": "inch", "timezone": "GMT",
            "start_date": str(start)[:10], "end_date": str(end)[:10],
        }
        payload = self._get(HISTORICAL_HOST + "/v1/forecast?" + urllib.parse.urlencode(params), "open-meteo historical forecast")
        hourly = payload.get("hourly")
        require(isinstance(hourly, Mapping), "open-meteo historical forecast: no hourly block")
        names = [m for m in str(models).split(",") if m]
        return {"models": names, "unit": "F", "precip_unit": "in", "days": previous_run_days(hourly, offset_hours, names, leads)}

    @staticmethod
    def bracket_probability(members: Any, low: Any = None, high: Any = None, smoothing: float = 0.5) -> float:
        return bracket_probability(members, low, high, smoothing)


__all__ = [
    "DEFAULT_MODELS",
    "ENSEMBLE_HOST",
    "ENSEMBLE_RUN_MODELS",
    "FORECAST_HOST",
    "FORECAST_RUN_MODELS",
    "HISTORICAL_HOST",
    "LEADS",
    "OpenMeteo",
    "USER_AGENT",
    "bracket_probability",
    "climate_day",
    "daily_highs",
    "ensemble_climate_days",
    "member_series",
    "previous_run_days",
    "summarize",
]

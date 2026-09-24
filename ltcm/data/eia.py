"""EIA spot and retail prices, for Kalshi's price series (kalshi-prices: KXWTI, KXBRENTD, KXDIESEL).

A free key the OWNER places (`EIA_API_KEY` in the House box's `.env`, never in the repository);
until then the House's `eia` recorder waits and polls nothing (league/feeds.py). The key rides in
the query string, as the API asks, so every error this module raises is redacted of it by the
recorder before it is stored or said.

    GET https://api.eia.gov/v2/<route>/data/?api_key=<key>&frequency=<daily|weekly>&data[0]=value
        &facets[series][]=<series>&sort[0][column]=period&sort[0][direction]=desc&length=<n>
      response.data[]: period ("2026-09-22"), series, series-description, value, units
      (https://www.eia.gov/opendata/documentation.php; UNVERIFIED on a probe: no key on Sept 24, 2026)

The series (EIA's own ids): WTI Cushing spot RWTC and Brent spot RBRTE (petroleum/pri/spt, daily),
US regular gasoline retail EMM_EPMR_PTE_NUS_DPG and on-highway diesel EMD_EPD2D_PTE_NUS_DPG
(petroleum/pri/gnd, weekly, Mondays). AAA's daily gasoline average, which KXAAAGAS* settles on, is
not EIA's and is not here.
"""

from __future__ import annotations

import math
import time
import urllib.parse
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

HOST = "https://api.eia.gov"
#: The key a strategy names -> (route, frequency, EIA series id, what it is).
SERIES = {
    "WTI": ("petroleum/pri/spt", "daily", "RWTC", "WTI crude, Cushing OK spot, $/barrel"),
    "BRENT": ("petroleum/pri/spt", "daily", "RBRTE", "Brent crude, Europe spot, $/barrel"),
    "GASOLINE": ("petroleum/pri/gnd", "weekly", "EMM_EPMR_PTE_NUS_DPG", "US regular gasoline retail, $/gallon (Mondays)"),
    "DIESEL": ("petroleum/pri/gnd", "weekly", "EMD_EPD2D_PTE_NUS_DPG", "US on-highway diesel retail, $/gallon (Mondays)"),
}
MIN_INTERVAL = 1.0


def parse_series(key: str, payload: Any, recent: int = 5) -> dict[str, Any]:
    """An EIA v2 answer for one series as `{series, period, value, units, recent}`: the newest period
    and its value, and the `recent` newest `[{period, value}]`. Raises DataError when the answer
    carries no numeric value of that series."""
    response = payload.get("response") if isinstance(payload, Mapping) else None
    rows = response.get("data") if isinstance(response, Mapping) else None
    require(isinstance(rows, list), f"eia {key}: no response.data" + (f" ({payload.get('error')})" if isinstance(payload, Mapping)
                                                                        and payload.get("error") else ""))
    wanted = SERIES[key][2]
    points = []
    for row in rows:
        if not isinstance(row, Mapping) or str(row.get("series") or "") != wanted:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        period = str(row.get("period") or "")[:10]
        if math.isfinite(value) and len(period) >= 7:
            points.append({"period": period, "value": value, "units": row.get("units")})
    require(points, f"eia {key}: no value of {wanted} in the answer")
    points.sort(key=lambda p: p["period"], reverse=True)
    return {"series": wanted, "what": SERIES[key][3], "period": points[0]["period"], "value": points[0]["value"],
            "units": points[0]["units"], "recent": [{"period": p["period"], "value": p["value"]} for p in points[:recent]]}


class Eia:
    """EIA's price series, read with the owner's key."""

    def __init__(self, api_key: str, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        if not api_key:
            raise DataError("eia: no key (EIA_API_KEY is the owner's to place)")
        self.api_key = str(api_key)
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def series(self, key: str) -> dict[str, Any]:
        name = str(key or "").upper()
        if name not in SERIES:
            raise DataError(f"eia: no series {key!r}")
        route, frequency, series_id, _ = SERIES[name]
        params = [("api_key", self.api_key), ("frequency", frequency), ("data[0]", "value"), ("facets[series][]", series_id),
                  ("sort[0][column]", "period"), ("sort[0][direction]", "desc"), ("length", "10")]
        url = f"{HOST}/v2/{route}/data/?" + urllib.parse.urlencode(params)
        return parse_series(name, read_json(self.transport, url, headers={"Accept": "application/json"}, timeout=self.timeout,
                                            what=f"eia {name}"))


__all__ = ["Eia", "HOST", "SERIES", "parse_series"]

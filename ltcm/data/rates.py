"""Reference rates and the Treasury par yield curve, for Kalshi's rates series (Sept 24, 2026).

Kalshi lists daily markets on SOFR (KXSOFRD) and on Treasury yields (KXUST2AD, KXUST10AD); both
settle on numbers two public sources publish once a business day. Neither publishes the moment a
number appeared -- the New York Fed's API answers an effective date, and every entry of the
Treasury's feed carries the same `<updated>` (the feed's own, probed Sept 24, 2026) -- so the House
stamps a number with when it first read it and never backfills it (`league/feeds.py`, the `rates`
and `treasury` feeds).

    GET https://markets.newyorkfed.org/api/rates/all/latest.json
      refRates[]: effectiveDate, type (SOFR, EFFR, OBFR, TGCR, BGCR, SOFRAI), percentRate,
                  percentPercentile1/25/75/99, volumeInBillions, revisionIndicator,
                  targetRateFrom/targetRateTo (EFFR), average30day/90day/180day and index (SOFRAI)
    GET https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml
        ?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM
      <m:properties>: <d:NEW_DATE>2026-09-23T00:00:00</d:NEW_DATE>, <d:BC_1MONTH>3.99</d:BC_1MONTH> ...
      <d:BC_30YEAR>; a tenor with no value is `m:null="true"` or absent. Slow: 17 s on Sept 24, 2026.

The Treasury answer is read with regular expressions, not an XML parser: it is a flat list of
number fields, and no entity in a response is ever expanded.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

NYFED_HOST = "https://markets.newyorkfed.org"
TREASURY_HOST = "https://home.treasury.gov"
REFERENCE_URL = NYFED_HOST + "/api/rates/all/latest.json"
PAR_YIELD_URL = TREASURY_HOST + "/resource-center/data-chart-center/interest-rates/pages/xml"
#: The reference rates the New York Fed publishes each business day.
REFERENCE_RATES = ("SOFR", "EFFR", "OBFR", "TGCR", "BGCR")
#: The Treasury's field for each tenor of the par yield curve, by the name a strategy uses.
TENORS = {"1M": "BC_1MONTH", "6W": "BC_1_5MONTH", "2M": "BC_2MONTH", "3M": "BC_3MONTH", "4M": "BC_4MONTH", "6M": "BC_6MONTH",
          "1Y": "BC_1YEAR", "2Y": "BC_2YEAR", "3Y": "BC_3YEAR", "5Y": "BC_5YEAR", "7Y": "BC_7YEAR", "10Y": "BC_10YEAR",
          "20Y": "BC_20YEAR", "30Y": "BC_30YEAR"}
MIN_INTERVAL = 1.0
_PROPERTIES = re.compile(r"<m:properties>(.*?)</m:properties>", re.S)
_FIELD = re.compile(r"<d:([A-Z0-9_]+)(?:\s[^>]*)?>([^<]*)</d:\1>")


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_reference_rates(payload: Any) -> dict[str, dict[str, Any]]:
    """The New York Fed's latest answer as `{type: {effective_date, rate, p1, p25, p75, p99,
    volume_bn, revised, ...}}` for the rates in `REFERENCE_RATES`. A type without a date or a rate
    is left out, never filled; an answer with no rate at all is a DataError."""
    rows = payload.get("refRates") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), "nyfed rates: no refRates")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("type") or "").upper()
        day, rate = str(row.get("effectiveDate") or "")[:10], _float(row.get("percentRate"))
        if kind not in REFERENCE_RATES or len(day) != 10 or rate is None:
            continue
        entry = {"type": kind, "effective_date": day, "rate": rate,
                 "p1": _float(row.get("percentPercentile1")), "p25": _float(row.get("percentPercentile25")),
                 "p75": _float(row.get("percentPercentile75")), "p99": _float(row.get("percentPercentile99")),
                 "volume_bn": _float(row.get("volumeInBillions")), "revised": bool(str(row.get("revisionIndicator") or "").strip())}
        if row.get("targetRateFrom") is not None:
            entry.update(target_from=_float(row.get("targetRateFrom")), target_to=_float(row.get("targetRateTo")))
        out[kind] = entry
    require(out, "nyfed rates: no reference rate in the answer")
    return out


def parse_par_yields(body: "bytes | str") -> list[dict[str, Any]]:
    """The Treasury's par yield curve feed as `[{date, yields: {tenor: percent}}]`, oldest first. A
    tenor with no value that day is absent from its `yields`."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    require("<feed" in text[:4000], "treasury par yields: not the yield curve feed")
    fields = {field: tenor for tenor, field in TENORS.items()}
    out = []
    for block in _PROPERTIES.findall(text):
        values = dict(_FIELD.findall(block))
        day = str(values.get("NEW_DATE") or "")[:10]
        if len(day) != 10:
            continue
        yields = {fields[name]: number for name, raw in values.items() if name in fields for number in (_float(raw),) if number is not None}
        if yields:
            out.append({"date": day, "yields": yields})
    out.sort(key=lambda row: row["date"])
    return out


class Rates:
    """The New York Fed's reference rates and the Treasury's par yield curve."""

    def __init__(self, transport: Any = None, *, timeout: float = 60.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def reference_rates(self) -> dict[str, dict[str, Any]]:
        payload = read_json(self.transport, REFERENCE_URL, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                            timeout=self.timeout, what="nyfed rates")
        return parse_reference_rates(payload)

    def par_yields(self, month: str) -> list[dict[str, Any]]:
        """The curve of every business day of `month` (YYYYMM) the Treasury has published so far."""
        if not re.fullmatch(r"\d{6}", str(month)):
            raise DataError(f"not a month: {month!r}")
        url = f"{PAR_YIELD_URL}?data=daily_treasury_yield_curve&field_tdr_date_value_month={month}"
        status, _, body = self.transport.get(url, {"Accept": "application/xml", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        if status != 200:
            raise DataError(f"treasury par yields: HTTP {status} from {url}")
        return parse_par_yields(body)


__all__ = ["NYFED_HOST", "PAR_YIELD_URL", "REFERENCE_RATES", "REFERENCE_URL", "Rates", "TENORS", "TREASURY_HOST",
           "parse_par_yields", "parse_reference_rates"]

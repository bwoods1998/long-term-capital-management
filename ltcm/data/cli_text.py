"""The NWS Daily Climate Report (CLI) as the National Weather Service issued it: the raw text product of
each settlement station, parsed (Sept 25, 2026, the Kalshi-scale run's `cli_text` recorder,
league/open_feeds_more.py).

Every Kalshi daily high, low and rain market settles on one station's CLI. The `cli` feed
(league/open_feeds.py) reads the Iowa Environmental Mesonet's parse of these reports and backfills
them; this one reads the NWS's own file, the moment it is replaced, which is faster and needs no
third party -- but holds only the newest report, so it cannot be backfilled.

    GET https://tgftp.nws.noaa.gov/data/raw/cd/cdus41.kokx.cli.nyc.txt
      CDUS41 KOKX 250633            <- the WMO header: the day of the month and the UTC time issued
      CLINYC
      ...
      233 AM EDT FRI SEP 25 2026    <- the local issue time and date
      ...THE CENTRAL PARK NY CLIMATE SUMMARY FOR SEPTEMBER 24 2026...
      VALID TODAY AS OF 0500 PM LOCAL TIME.   <- only in a same-day (preliminary) report
      TEMPERATURE (F)
       YESTERDAY | TODAY
        MAXIMUM         66    305 PM  91    2017  73 ...
        MINIMUM         53    644 AM  ...
      PRECIPITATION (IN)
        YESTERDAY        0.00 ...     (T is a trace, MM missing)
      SNOWFALL (IN)
        YESTERDAY        0.0 ...

Each settlement station's file is named by its WMO header and office (verified Sept 25, 2026 against
the NWS product ids the IEM holds): every one of the twenty in ltcm/data/weather.py answered except New
Orleans (cdus44.klix.cli.msy.txt answered a 301 to a directory), which is left out.

Terms (read Sept 25, 2026): https://www.weather.gov/disclaimer -- NWS information is in the public domain
"and may be used without charge for any lawful purpose"; the NWS may block addresses that query too often,
so a station is asked at most every ten minutes and a failure is not retried within a minute.
"""

from __future__ import annotations

import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

HOST = "https://tgftp.nws.noaa.gov"
#: Settlement station -> the file its CLI is kept under (/data/raw/cd/<name>.txt).
FILES: dict[str, str] = {
    "KNYC": "cdus41.kokx.cli.nyc", "KMDW": "cdus43.klot.cli.mdw", "KMIA": "cdus42.kmfl.cli.mia", "KAUS": "cdus44.kewx.cli.aus",
    "KDEN": "cdus45.kbou.cli.den", "KLAX": "cdus46.klox.cli.lax", "KPHL": "cdus41.kphi.cli.phl", "KSEA": "cdus46.ksew.cli.sea",
    "KATL": "cdus42.kffc.cli.atl", "KHOU": "cdus44.khgx.cli.hou", "KDFW": "cdus44.kfwd.cli.dfw", "KPHX": "cdus45.kpsr.cli.phx",
    "KBOS": "cdus41.kbox.cli.bos", "KDCA": "cdus41.klwx.cli.dca", "KLAS": "cdus45.kvef.cli.las", "KSFO": "cdus46.kmtr.cli.sfo",
    "KMSP": "cdus43.kmpx.cli.msp", "KOKC": "cdus44.koun.cli.okc", "KSAT": "cdus44.kewx.cli.sat",
}
MIN_INTERVAL = 0.5
_MONTHS = {name: i for i, name in enumerate(("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER",
                                             "OCTOBER", "NOVEMBER", "DECEMBER"), 1)}
_SHORT = {name[:3]: i for name, i in _MONTHS.items()}
_HEADER = re.compile(r"^\s*(CDUS\d\d)\s+(K[A-Z]{3})\s+(\d{2})(\d{2})(\d{2})", re.M)
_ISSUED = re.compile(r"^\s*\d{3,4}\s+[AP]M\s+[A-Z]{3}\s+[A-Z]{3}\s+([A-Z]{3})\s+(\d{1,2})\s+(\d{4})\s*$", re.M)
_SUMMARY = re.compile(r"CLIMATE SUMMARY FOR\s+([A-Z]+)\s+(\d{1,2})\s+(\d{4})")
_AS_OF = re.compile(r"VALID (?:TODAY )?AS OF\s+(\d{3,4}\s+[AP]M)")
_NUMBER = r"(-?\d+(?:\.\d+)?|T|MM)R?"


def _reading(text: str) -> float | None:
    if text in (None, "", "MM"):
        return None
    if text == "T":
        return 0.0001
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _block(text: str, title: str) -> str:
    """The lines of a report's section (TEMPERATURE (F), PRECIPITATION (IN) ...) up to the next blank line."""
    start = text.find(title)
    if start < 0:
        return ""
    end = text.find("\n\n", start)
    return text[start:end if end > 0 else len(text)]


def _line(block: str, name: str) -> re.Match | None:
    return re.search(rf"^\s+{name}\s+{_NUMBER}(?:\s+(\d{{1,2}}:?\d{{2}}\s+[AP]M))?", block, re.M)


def issue_time(text: str) -> float:
    """The UTC moment the product was issued: the WMO header's day, hour and minute, in the month and year of
    the product's own (local) issue date -- the header's day is within a day of it."""
    header, local = _HEADER.search(text), _ISSUED.search(text)
    require(header is not None and local is not None, "nws cli: no WMO header or issue line")
    day, hour, minute = int(header.group(3)), int(header.group(4)), int(header.group(5))
    require(local.group(1) in _SHORT, "nws cli: unreadable issue date")
    around = date(int(local.group(3)), _SHORT[local.group(1)], int(local.group(2)))
    for shift in (0, 1, -1):  # the header's day in this month, or the next or last one near a month's end
        index = around.year * 12 + around.month - 1 + shift
        try:
            candidate = date(index // 12, index % 12 + 1, day)
        except ValueError:
            continue
        if abs((candidate - around).days) <= 1:
            return datetime(candidate.year, candidate.month, candidate.day, hour, minute, tzinfo=timezone.utc).timestamp()
    raise DataError("nws cli: the WMO header's day is not within a day of the issue date")


def parse_cli(body: "bytes | str") -> dict[str, Any]:
    """One CLI product as {office, product, issued (UTC ISO), issued_at, date (the climate day), preliminary,
    as_of, high, high_time, low, low_time, precip_in, snow_in}. DataError when it is not a climate report."""
    text = (body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)).replace("\r", "")
    require("CLIMATE REPORT" in text[:600], "nws cli: not a climate report")
    at = issue_time(text)
    header = _HEADER.search(text)
    summary = _SUMMARY.search(text)
    require(summary is not None and summary.group(1) in _MONTHS, "nws cli: no climate summary date")
    day = date(int(summary.group(3)), _MONTHS[summary.group(1)], int(summary.group(2)))
    temperature = _block(text, "TEMPERATURE (F)")
    high, low = _line(temperature, "MAXIMUM"), _line(temperature, "MINIMUM")
    precip = _line(_block(text, "PRECIPITATION (IN)"), "(?:YESTERDAY|TODAY)")
    snow = _line(_block(text, "SNOWFALL (IN)"), "(?:YESTERDAY|TODAY)")
    as_of = _AS_OF.search(text)
    product = re.search(r"^(CLI[A-Z]{3})\s*$", text, re.M)
    return {"office": header.group(2), "wmo": header.group(1), "product": product.group(1) if product else None,
            "issued": datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "issued_at": at,
            "date": day.isoformat(), "preliminary": as_of is not None, "as_of": as_of.group(1) if as_of else None,
            "high": _reading(high.group(1)) if high else None, "high_time": high.group(2) if high and high.group(2) else None,
            "low": _reading(low.group(1)) if low else None, "low_time": low.group(2) if low and low.group(2) else None,
            "precip_in": _reading(precip.group(1)) if precip else None, "snow_in": _reading(snow.group(1)) if snow else None}


class ClimateText:
    """The NWS's raw CLI text products of the settlement stations, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 20.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def latest(self, station: str) -> dict[str, Any]:
        name = FILES.get(str(station).upper())
        if name is None:
            raise DataError(f"nws cli: no raw CLI file is known for {station!r}")
        url = f"{HOST}/data/raw/cd/{name}.txt"
        status, _, body = self.transport.get(url, {"Accept": "text/plain", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        if status != 200:
            raise DataError(f"nws cli: HTTP {status} from {url}")
        return parse_cli(body)


__all__ = ["FILES", "HOST", "ClimateText", "issue_time", "parse_cli"]

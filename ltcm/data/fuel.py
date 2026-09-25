"""EIA's public price tables, read without a key (Sept 25, 2026, the Kalshi-scale run's `fuel` recorder,
league/open_feeds_more.py). Source: U.S. Energy Information Administration.

The House's keyed `eia` recorder (api.eia.gov) waits for the owner's key; the same numbers are on EIA's
public website as HTML history tables, which need none. Kalshi's gasoline series (KXAAAGAS*) settle on
AAA's daily average, which is a different number from a different source (gasprices.aaa.com offers no
terms that allow automated access); EIA's weekly retail price is the government's own series beside it.

    GET https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=EMM_EPMR_PTE_NUS_DPG&f=W   (weekly)
      <tr><td class='B6'>&nbsp;&nbsp;2026-Sep</td> then up to five pairs <td class='B5'>09/07&nbsp;</td>
      <td class='B3'>4.157&nbsp;...</td> (the week's END date, the price); "Release Date: 9/22/2026" and
      "Next Release Date: 9/29/2026" under the table. Slow: 3-8 s (Sept 25, 2026).
    GET https://www.eia.gov/dnav/pet/hist/RWTCD.htm   (daily; LeafHandler answers a 302 to this)
      <tr><td class='B6'>&nbsp;&nbsp;2026 Sep-21 to Sep-25</td> then five <td class='B3'>96.97</td> cells,
      Monday to Friday, empty for a day with no price; the same release dates. About 0.47 MB (since 1986).

Terms (read Sept 25, 2026): https://www.eia.gov/about/copyrights_reuse.php -- EIA's data are in the
public domain and "You may use and/or distribute any of our data", citing "Source: U.S. Energy
Information Administration"; robots.txt does not disallow /dnav/.
"""

from __future__ import annotations

import html
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

HOST = "https://www.eia.gov"
#: The series, by the key a strategy names: (EIA's page, frequency, what, unit).
SERIES: dict[str, tuple[str, str, str, str]] = {
    "GASOLINE": ("/dnav/pet/hist/LeafHandler.ashx?n=PET&s=EMM_EPMR_PTE_NUS_DPG&f=W", "weekly",
                 "U.S. regular all formulations retail gasoline price (EMM_EPMR_PTE_NUS_DPG)", "dollars per gallon"),
    "DIESEL": ("/dnav/pet/hist/LeafHandler.ashx?n=PET&s=EMD_EPD2D_PTE_NUS_DPG&f=W", "weekly",
               "U.S. No 2 diesel retail price (EMD_EPD2D_PTE_NUS_DPG)", "dollars per gallon"),
    "WTI": ("/dnav/pet/hist/RWTCD.htm", "daily", "Cushing, OK WTI spot price FOB (RWTC)", "dollars per barrel"),
    "BRENT": ("/dnav/pet/hist/RBRTED.htm", "daily", "Europe Brent spot price FOB (RBRTE)", "dollars per barrel"),
}
MIN_INTERVAL = 2.0
_ROW = re.compile(r"<tr>\s*<td class='B6'>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td class='(B[35])'>(.*?)</td>", re.S)
_WEEK = re.compile(r"(\d{4})\s+([A-Z][a-z]{2})-\s*(\d{1,2})\s+to\s+([A-Z][a-z]{2})-\s*(\d{1,2})")
_MONTH = re.compile(r"(\d{4})-([A-Z][a-z]{2})")
_RELEASE = re.compile(r"(?<!Next )Release Date:\s*(\d{1,2})/(\d{1,2})/(\d{4})")
_NEXT = re.compile(r"Next Release Date:\s*(\d{1,2})/(\d{1,2})/(\d{4})")
_MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def _clean(cell: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split())


def _value(text: str) -> float | None:
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _release(pattern: re.Pattern, text: str) -> str | None:
    found = pattern.search(text)
    return date(int(found.group(3)), int(found.group(1)), int(found.group(2))).isoformat() if found else None


def parse_weekly(body: "bytes | str") -> list[dict[str, Any]]:
    """A weekly history table as [{date (the week's end), value}], oldest first."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    out = []
    for row in _ROW.findall(text):
        label = _MONTH.search(_clean(row.split("</td>", 1)[0]))
        if label is None:
            continue
        year = int(label.group(1))
        cells = _CELL.findall(row)
        for (kind_a, day), (kind_b, value) in zip(cells[0::2], cells[1::2]):
            if kind_a != "B5" or kind_b != "B3":
                continue
            day, number = _clean(day), _value(_clean(value))
            found = re.fullmatch(r"(\d{2})/(\d{2})", day)
            if found and number is not None:
                out.append({"date": date(year, int(found.group(1)), int(found.group(2))).isoformat(), "value": number})
    out.sort(key=lambda r: r["date"])
    return out


def parse_daily(body: "bytes | str") -> list[dict[str, Any]]:
    """A daily history table (a row a week, Monday to Friday) as [{date, value}], oldest first."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    out = []
    for row in _ROW.findall(text):
        label = _WEEK.search(_clean(row.split("</td>", 1)[0]))
        if label is None or label.group(2) not in _MONTHS:
            continue
        monday = date(int(label.group(1)), _MONTHS[label.group(2)], int(label.group(3)))
        cells = [value for kind, value in _CELL.findall(row) if kind == "B3"]
        for offset, value in enumerate(cells[:5]):
            number = _value(_clean(value))
            if number is not None:
                out.append({"date": (monday + timedelta(days=offset)).isoformat(), "value": number})
    out.sort(key=lambda r: r["date"])
    return out


def parse_table(body: "bytes | str", frequency: str) -> dict[str, Any]:
    """{values (oldest first), release_date, next_release} from one EIA history page; DataError when it has no values."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    values = parse_weekly(text) if frequency == "weekly" else parse_daily(text)
    require(values, "eia: the history table has no readable value")
    return {"values": values, "release_date": _release(_RELEASE, text), "next_release": _release(_NEXT, text)}


class Fuel:
    """EIA's public weekly retail and daily spot price tables, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 60.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def series(self, key: str, recent: int = 10) -> dict[str, Any]:
        if key not in SERIES:
            raise DataError(f"eia: no series {key!r}")
        path, frequency, what, unit = SERIES[key]
        status, _, body = self.transport.get(HOST + path, {"Accept": "text/html", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        if status != 200:
            raise DataError(f"eia: HTTP {status} from {HOST + path}")
        table = parse_table(body, frequency)
        values = table["values"]
        return {"series": key, "what": what, "unit": unit, "frequency": frequency, "latest": values[-1],
                "recent": values[-int(recent):], "release_date": table["release_date"], "next_release": table["next_release"],
                "source": "U.S. Energy Information Administration"}


__all__ = ["HOST", "SERIES", "Fuel", "parse_daily", "parse_table", "parse_weekly"]

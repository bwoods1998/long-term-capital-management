"""US macro data for Kalshi's economics markets: BLS series and the Federal Reserve calendar.

Kalshi lists markets on the CPI print, the unemployment rate, payrolls and every FOMC decision.
The Bureau of Labor Statistics publishes the series those markets settle on, and the Federal
Reserve Board publishes the calendar of FOMC meetings, minutes and press conferences. Both are
keyless; nothing here trades.

Hosts, endpoints and the fields relied on (probed live Sept 18, 2026):

    https://api.bls.gov
        POST /publicAPI/v2/timeseries/data/   body {"seriesid": [...], "startyear": "2025",
                                              "endyear": "2026"}  (Content-Type: application/json)
            status ("REQUEST_SUCCEEDED"), message[] (limit warnings as strings),
            Results.series[]: seriesID, data[]: year, period ("M08"; "M13" is the annual
            average; "Q01".."Q05"; "S01".."S03"), periodName, value (decimal string),
            latest ("true" on the newest row only), footnotes[]: {code, text} or {}
        Without a registration key v2 allows 25 queries a day, 25 series a query and a
        10-year window (https://www.bls.gov/developers/api_faqs.htm). A 25-series batch a few
        times a day fits; `bls_series()` clips the window and the id list to those limits.
        There is no keyless release schedule endpoint (`/publicAPI/v2/schedule` answers 404),
        so `next_releases()` returns an empty list and says so in its docstring.
    https://www.federalreserve.gov
        GET /json/calendar.json     (UTF-8 with a byte-order mark; ~540 KB, every year's events)
            events[]: title, type ("FOMC", "Beige", "Testimony", "Speeches", "Stat", ...),
                      month ("2026-10"), days ("28" or "27-28"), time ("2:00 p.m."),
                      description (HTML-escaped), link/live (URLs), location
            A few historical `other` rows carry `day` instead of `days` and an empty month;
            those never reach a caller.

Series ids the desk uses by default: CUUR0000SA0 (CPI-U all items, NSA), LNS14000000
(unemployment rate, SA), CES0000000001 (total nonfarm payrolls, SA, thousands). Values come
back as floats; periods as ISO-ish strings ("2026-08", "2026", "2026-Q3").
"""

from __future__ import annotations

import html
import json
import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, TransportError, iso, strip_html

BLS_HOST = "https://api.bls.gov"
FED_HOST = "https://www.federalreserve.gov"
BLS_SERIES_URL = BLS_HOST + "/publicAPI/v2/timeseries/data/"
FED_CALENDAR_URL = FED_HOST + "/json/calendar.json"
USER_AGENT = CONTACT_USER_AGENT  # one constant for the whole package (ltcm/data/__init__.py)
SOURCE = "macro"

#: 25 keyless BLS queries a day: one a second is a courtesy, the daily budget is the limit.
MIN_INTERVAL = 1.0
DEFAULT_SERIES = ("CUUR0000SA0", "LNS14000000", "CES0000000001")
#: Keyless v2 limits (https://www.bls.gov/developers/api_faqs.htm).
BLS_MAX_SERIES = 25
BLS_MAX_YEARS = 10
#: Calendar types a desk prices; everything else on the Fed calendar is speeches and stat releases.
FOMC_TYPES = ("FOMC",)


def _float(value: Any) -> "float | None":
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def period_key(year: Any, period: Any) -> "str | None":
    """BLS (year, period) -> "2026-08", "2026" (M13 annual), "2026-Q3", "2026-S1"; None if odd."""
    year_text = str(year or "").strip()
    code = str(period or "").strip().upper()
    if not (len(year_text) == 4 and year_text.isdigit() and len(code) == 3 and code[1:].isdigit()):
        return None
    number = int(code[1:])
    if code[0] == "M":
        return year_text if number == 13 else f"{year_text}-{number:02d}" if 1 <= number <= 12 else None
    if code[0] == "Q":
        return year_text if number == 5 else f"{year_text}-Q{number}" if 1 <= number <= 4 else None
    if code[0] == "S":
        return year_text if number == 3 else f"{year_text}-S{number}" if 1 <= number <= 2 else None
    if code[0] == "A":
        return year_text
    return None


def _footnotes(rows: Any) -> list[str]:
    out = []
    for note in rows if isinstance(rows, list) else []:
        if isinstance(note, Mapping) and note.get("text"):
            out.append(str(note["text"]))
    return out


def _clean(value: Any) -> "str | None":
    """Fed calendar text is HTML-escaped HTML; unescape, strip tags, collapse whitespace."""
    if not isinstance(value, str) or not value:
        return None
    text = strip_html(html.unescape(value))
    text = " ".join(text.split())
    return text or None


def calendar_row(event: Any) -> "dict[str, Any] | None":
    """One Fed calendar event as `{date, end_date, title, type, time, description, link}`."""
    if not isinstance(event, Mapping):
        return None
    month = str(event.get("month") or "").strip()
    days = str(event.get("days") or event.get("day") or "").strip()
    if len(month) != 7 or month[4] != "-" or not days:
        return None
    parts = [p.strip() for p in days.replace("–", "-").split("-") if p.strip().isdigit()]
    if not parts:
        return None
    try:
        start = datetime.strptime(f"{month}-{int(parts[0]):02d}", "%Y-%m-%d").date().isoformat()
        end = datetime.strptime(f"{month}-{int(parts[-1]):02d}", "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None
    title = _clean(event.get("title"))
    if title is None:
        return None
    return {
        "date": start,
        "end_date": end,
        "title": title,
        "type": str(event.get("type") or "").strip() or None,
        "time": _clean(event.get("time")),
        "description": _clean(event.get("description")),
        "link": str(event.get("link") or event.get("live") or "") or None,
    }


class Macro:
    """BLS time series and the Federal Reserve Board's public calendar."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 30.0,
        cache_dir: Any = None,
        cache_ttl: float = 3600.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock

    def _today(self):
        return datetime.fromtimestamp(float(self.clock()), tz=timezone.utc).date()

    # -------------------------------------------------------------------- BLS
    def bls_series(self, series_ids: Any = DEFAULT_SERIES, years: int = 2) -> dict[str, list[dict[str, Any]]]:
        """`{series_id: [{period, value, period_name, latest, footnotes}]}`, newest first.

        A series BLS did not return is present with an empty list, so a caller can tell a
        quiet series from a bad request; the request itself failing raises `DataError`."""
        ids = [str(s).strip() for s in (series_ids or ()) if str(s).strip()][:BLS_MAX_SERIES]
        if not ids:
            raise DataError("bls: no series ids")
        end_year = self._today().year
        span = max(1, min(int(years), BLS_MAX_YEARS))
        body = {"seriesid": ids, "startyear": str(end_year - span + 1), "endyear": str(end_year)}
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        status, _, raw = self.transport.request(
            "POST", BLS_SERIES_URL, headers=headers, body=json.dumps(body).encode("utf-8"), timeout=self.timeout
        )
        if status != 200:
            raise DataError(f"bls: HTTP {status} from {BLS_SERIES_URL}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DataError("bls: malformed JSON") from exc
        if not isinstance(payload, Mapping) or str(payload.get("status")) != "REQUEST_SUCCEEDED":
            messages = payload.get("message") if isinstance(payload, Mapping) else None
            detail = "; ".join(str(m) for m in messages) if isinstance(messages, list) and messages else "request failed"
            raise DataError(f"bls: {detail}")
        results = payload.get("Results")
        series = results.get("series") if isinstance(results, Mapping) else None
        out: dict[str, list[dict[str, Any]]] = {sid: [] for sid in ids}
        for entry in series if isinstance(series, list) else []:
            if not isinstance(entry, Mapping):
                continue
            sid = str(entry.get("seriesID") or "")
            rows = []
            for point in entry.get("data") if isinstance(entry.get("data"), list) else []:
                if not isinstance(point, Mapping):
                    continue
                period = period_key(point.get("year"), point.get("period"))
                value = _float(point.get("value"))
                if period is None or value is None:
                    continue
                rows.append(
                    {
                        "period": period,
                        "value": value,
                        "period_name": str(point.get("periodName") or "") or None,
                        "latest": str(point.get("latest")).lower() == "true",
                        "footnotes": _footnotes(point.get("footnotes")),
                    }
                )
            rows.sort(key=lambda row: row["period"], reverse=True)
            if sid:
                out[sid] = rows
        return out

    # -------------------------------------------------------------------- Fed
    def fed_calendar(self, types: Any = FOMC_TYPES, include_past: bool = False) -> list[dict[str, Any]]:
        """Upcoming Fed calendar rows of the given types (FOMC by default), soonest first.

        `types=None` keeps every type. Never raises: an unreachable or reshaped calendar
        answers an empty list."""
        try:
            status, _, raw = self.transport.get(FED_CALENDAR_URL, {"Accept": "application/json", "User-Agent": USER_AGENT}, self.timeout)
        except (DataError, TransportError):
            return []
        if status != 200:
            return []
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            return []
        events = payload.get("events") if isinstance(payload, Mapping) else None
        if not isinstance(events, list):
            return []
        wanted = None if types is None else {str(t).lower() for t in types}
        today = self._today().isoformat()
        out = []
        for event in events:
            row = calendar_row(event)
            if row is None:
                continue
            if wanted is not None and str(row["type"] or "").lower() not in wanted:
                continue
            if not include_past and row["end_date"] < today:
                continue
            out.append(row)
        out.sort(key=lambda row: (row["date"], row["time"] or "", row["title"]))
        return out

    def next_fomc(self) -> "dict[str, Any] | None":
        """The next FOMC meeting decision day (the row titled "FOMC Meeting"), or None."""
        for row in self.fed_calendar():
            if row["title"].lower().startswith("fomc meeting"):
                return row
        return None

    def next_releases(self) -> list[dict[str, Any]]:
        """BLS release dates. Always empty: BLS publishes its schedule only as HTML pages
        (https://www.bls.gov/schedule/news_release/), and the v2 API has no keyless schedule
        endpoint (`/publicAPI/v2/schedule` answered 404 on Sept 18, 2026). Kept so a desk can
        call it without a branch; fill it in when a JSON schedule appears."""
        return []


__all__ = [
    "BLS_HOST",
    "BLS_SERIES_URL",
    "DEFAULT_SERIES",
    "FED_CALENDAR_URL",
    "FED_HOST",
    "FOMC_TYPES",
    "Macro",
    "USER_AGENT",
    "calendar_row",
    "period_key",
]

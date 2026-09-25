"""When the statistical agencies release what Kalshi's economics markets settle on: the Bureau of Labor
Statistics' release calendar and the Bureau of Economic Analysis' release schedule (Sept 25, 2026, the
Kalshi-scale run's `releases` recorder, league/open_feeds.py).

KXCPI, KXCPIYOY, KXCPICORE, KXU3 and KXPAYROLLS settle on BLS releases, KXGDP on BEA's; a strategy that
knows the moment a number comes out knows when its market will move and resolve.

    GET https://www.bls.gov/schedule/news_release/bls.ics   (text/calendar)
      VEVENT: DTSTART;TZID=US-Eastern:20260101T083000, SUMMARY:Consumer Price Index, ... -- every
      release of the year and the last (313 events on Sept 25, 2026; Last-Modified Jun 10, 2026)
    GET https://www.bea.gov/news/schedule   (HTML)
      <table id="release-schedule-table">, thead "Year 2026", rows: <div class="release-date">September 30</div>
      <small class="text-muted">8:30 AM</small>, the release type (News or Data, by the row's class) and
      <td class="release-title ...">GDP (Third Estimate), ...</td>

Terms (read Sept 25, 2026): BLS -- https://www.bls.gov/bls/linksite.htm: "everything that we publish ...
is in the public domain ... You are free to use our public domain material without specific permission"
(cite BLS); robots.txt does not disallow /schedule/news_release/. BEA -- a federal agency whose works are
not copyrighted (17 U.S.C. 105); https://www.bea.gov/help/guidelines-for-citing-bea asks only for
citation, no BEA policy page restricts automated access, and robots.txt does not disallow /news/. Both
answered the House's contact User-Agent with the page, no bot wall.
"""

from __future__ import annotations

import html
import re
import time
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
NEW_YORK = ZoneInfo("America/New_York")
MIN_INTERVAL = 2.0
_EVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)
_MONTHS = {name: i for i, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September",
                                             "October", "November", "December"), 1)}


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unfold(text: str) -> str:
    """iCalendar lines continue on the next line when it starts with a space."""
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def parse_bls_ics(body: "bytes | str") -> list[dict[str, Any]]:
    """BLS's calendar as [{agency, release, at (UTC ISO), date, time_et}], soonest first."""
    text = _unfold(body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body))
    require("BEGIN:VCALENDAR" in text[:200], "bls calendar: not an iCalendar file")
    out = []
    for block in _EVENT.findall(text):
        start = re.search(r"^DTSTART(?:;TZID=[^:]+)?:(\d{8})T(\d{4})", block, re.M)
        summary = re.search(r"^SUMMARY:(.*)$", block, re.M)
        if not start or not summary:
            continue
        local = datetime.strptime(start.group(1) + start.group(2), "%Y%m%d%H%M").replace(tzinfo=NEW_YORK)
        name = summary.group(1).strip().replace("\\,", ",").replace("\\;", ";")
        out.append({"agency": "BLS", "release": name, "at": _iso(local), "date": local.date().isoformat(), "time_et": local.strftime("%H:%M")})
    require(out, "bls calendar: no event")
    out.sort(key=lambda row: (row["at"], row["release"]))
    return out


def _clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_bea_schedule(body: "bytes | str") -> list[dict[str, Any]]:
    """BEA's release schedule as [{agency, release, kind (news or data ...), at (UTC ISO), date, time_et}], soonest first."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    tables = re.findall(r"<table[^>]*release-schedule-table.*?</table>", text, re.S)
    require(tables, "bea schedule: no release schedule table")
    out = []
    for table in tables:
        year = re.search(r"Year\s+(\d{4})", table)
        if year is None:
            continue
        for row in re.findall(r"<tr class=\"scheduled-releases-type-([a-z-]+)\"[^>]*>(.*?)</tr>", table, re.S):
            kind, cells = row
            day = re.search(r"release-date\">\s*([A-Z][a-z]+)\s+(\d{1,2})\s*<", cells)
            clock = re.search(r"<small[^>]*>\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*</small>", cells)
            title = re.search(r"<td class=\"release-title[^\"]*\"[^>]*>(.*?)</td>", cells, re.S)
            if not day or day.group(1) not in _MONTHS or not title:
                continue
            hour = int(clock.group(1)) % 12 + (12 if clock and clock.group(3) == "PM" else 0) if clock else 0
            local = datetime(int(year.group(1)), _MONTHS[day.group(1)], int(day.group(2)), hour,
                             int(clock.group(2)) if clock else 0, tzinfo=NEW_YORK)
            out.append({"agency": "BEA", "release": _clean(title.group(1)), "kind": kind, "at": _iso(local),
                        "date": local.date().isoformat(), "time_et": local.strftime("%H:%M") if clock else None})
    require(out, "bea schedule: no release in the table")
    out.sort(key=lambda row: (row["at"], row["release"]))
    return out


class Calendars:
    """BLS's release calendar and BEA's release schedule, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _page(self, url: str, accept: str, what: str) -> bytes:
        status, _, body = self.transport.get(url, {"Accept": accept, "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        head = body[:3000].lower()
        if status in (403, 429) and (b"captcha" in head or b"access denied" in head or b"challenge" in head):
            from .attention import Blocked

            raise Blocked(f"{what}: the site answered a bot check (HTTP {status}), not the page")
        if status != 200:
            raise DataError(f"{what}: HTTP {status} from {url}")
        return body

    def bls(self) -> list[dict[str, Any]]:
        return parse_bls_ics(self._page(BLS_ICS_URL, "text/calendar", "bls calendar"))

    def bea(self) -> list[dict[str, Any]]:
        return parse_bea_schedule(self._page(BEA_SCHEDULE_URL, "text/html", "bea schedule"))


def upcoming(rows: list[dict[str, Any]], now: float, days: int) -> list[dict[str, Any]]:
    """The releases from the start of today (UTC) to `days` ahead."""
    today = datetime.fromtimestamp(float(now), timezone.utc).date().isoformat()
    until = datetime.fromtimestamp(float(now) + days * 86400.0, timezone.utc).date().isoformat()
    return [row for row in rows if today <= row["date"] <= until]


__all__ = ["BEA_SCHEDULE_URL", "BLS_ICS_URL", "Calendars", "parse_bea_schedule", "parse_bls_ics", "upcoming"]

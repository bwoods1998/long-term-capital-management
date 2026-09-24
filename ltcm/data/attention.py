"""The numbers Kalshi's attention markets settle on, from the pages that publish them (Sept 24, 2026).

KXTSAW settles on the TSA's checkpoint throughput and KXTRUMPAPPROVE on a polling average. Both are
HTML pages meant for people, so they are parsed defensively: a page that has changed shape is a
failed poll with the reason, never a guessed number. Neither page publishes when a figure appeared,
so the House stamps what it reads with when it read it and never backfills it (`league/feeds.py`,
the `tsa` and `polls` feeds).

    GET https://www.tsa.gov/travel/passenger-volumes
      one <table>: <th>Date</th><th>Numbers</th>, then <tr><td>9/22/2026</td><td>2,077,346</td></tr>
      ... newest first, the year to date (266 rows on Sept 24, 2026)
    GET https://www.realclearpolling.com/polls/approval/donald-trump/approval-rating
      Sept 24, 2026: HTTP 403 with a DataDome captcha to any automated client, a browser
      User-Agent included. The House does not get around a bot wall: that answer is recorded as
      `blocked`. Were the page served, its "RCP Average" row -- the average's dates, approve,
      disapprove, spread -- is what `parse_rcp_average` reads (UNVERIFIED against a served page).
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime
from typing import Any

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"
RCP_APPROVAL_URL = "https://www.realclearpolling.com/polls/approval/donald-trump/approval-rating"
MIN_INTERVAL = 2.0
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_AVERAGE = re.compile(r"RCP\s+Average\s+(\d{1,2}/\d{1,2}\s*-\s*\d{1,2}/\d{1,2})?\s*(?:--\s*)?(\d{1,2}(?:\.\d)?)\s+(\d{1,2}(?:\.\d)?)", re.I)


class Blocked(DataError):
    """The site refused an automated client outright (a bot wall), which no retry changes."""


def _cells(row: str) -> list[str]:
    return [" ".join(re.sub(r"<[^>]+>", " ", cell).split()) for cell in _CELL.findall(row)]


def parse_tsa(body: "bytes | str") -> list[dict[str, Any]]:
    """The TSA's checkpoint table as `[{date, travelers}]`, newest first. Raises DataError unless the
    page has the table with its Date and Numbers headers and at least one readable row."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    start = text.lower().find("<table")
    require(start >= 0, "tsa: no table on the page")
    table = text[start:text.lower().find("</table>", start)]
    rows = _ROW.findall(table)
    require(rows and [c.lower() for c in _cells(rows[0])][:2] == ["date", "numbers"], "tsa: the table is not Date / Numbers")
    out = []
    for row in rows[1:]:
        cells = _cells(row)
        if len(cells) < 2:
            continue
        try:
            day = datetime.strptime(cells[0], "%m/%d/%Y").date().isoformat()
            travelers = int(cells[1].replace(",", ""))
        except ValueError:
            continue
        if travelers > 0:
            out.append({"date": day, "travelers": travelers})
    require(out, "tsa: no readable row in the table")
    out.sort(key=lambda row: row["date"], reverse=True)
    return out


def blocked_reason(status: int, body: bytes) -> str | None:
    """Why the answer is a bot wall rather than the page, or None."""
    head = body[:4000].lower()
    if b"captcha-delivery" in head or b"datadome" in head:
        return f"the site answered a bot check (DataDome captcha, HTTP {status}), not the page"
    if status in (401, 403, 429) and (b"captcha" in head or b"cf-chl" in head or b"challenge" in head):
        return f"the site answered a bot check (HTTP {status}), not the page"
    return None


def parse_rcp_average(body: "bytes | str") -> dict[str, Any]:
    """The "RCP Average" row of a RealClearPolling approval page: `{approve, disapprove, spread,
    dates}`. Raises DataError when the page carries no such row."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
    found = _AVERAGE.search(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split()))  # every tag a space: cells stay apart
    require(found is not None, "rcp: no RCP Average row on the page")
    approve, disapprove = float(found.group(2)), float(found.group(3))
    require(0 < approve < 100 and 0 < disapprove < 100 and approve + disapprove <= 100.5, "rcp: the average's numbers are not percentages")
    return {"approve": approve, "disapprove": disapprove, "spread": round(approve - disapprove, 1),
            "dates": " ".join((found.group(1) or "").split()) or None}


class Attention:
    """The TSA's checkpoint numbers and the RCP approval average, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _page(self, url: str, what: str) -> bytes:
        status, _, body = self.transport.get(url, {"Accept": "text/html", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        reason = blocked_reason(status, body)
        if reason:
            raise Blocked(f"{what}: {reason}")
        if status != 200:
            raise DataError(f"{what}: HTTP {status} from {url}")
        return body

    def tsa(self) -> list[dict[str, Any]]:
        return parse_tsa(self._page(TSA_URL, "tsa"))

    def approval(self) -> dict[str, Any]:
        return parse_rcp_average(self._page(RCP_APPROVAL_URL, "rcp"))


__all__ = ["Attention", "Blocked", "RCP_APPROVAL_URL", "TSA_URL", "blocked_reason", "parse_rcp_average", "parse_tsa"]

"""Nasdaq's earnings date for a stock: the next announcement as the calendar shows it now.

The alpaca-megacaps and alpaca-options desks trade around earnings, and the House's history of
announcements (8-K Item 2.02 acceptance times, `ltcm/data/edgar.py`) says only when past ones came
out. Nasdaq's per-symbol page says when the next one is expected, and whether that date is the
company's own or Zacks' estimate from its past reporting dates. It publishes no time a date first
appeared, so the House stamps what it reads with when it read it and never backfills it
(`league/feeds.py`, the `earnings_date` feed).

    GET https://api.nasdaq.com/api/analyst/<SYMBOL>/earnings-date
      data.announcement  "Earnings announcement* for AAPL: Oct 29, 2026"
      data.reportText    "Apple Inc. Common Stock is estimated to report earnings on 10/29/2026. The
                          upcoming earnings date is derived from an algorithm based on a company's
                          historical reporting dates. ... based on 8 analysts' forecasts, the consensus
                          EPS forecast for the quarter is $1.98. The reported EPS for the same quarter
                          last year was $1.85."
      (probed Sept 24, 2026)

Nasdaq's edge answers a request with a plain client User-Agent by holding the connection open
(the contact User-Agent timed out after 25 s on Sept 24, 2026); the page's own headers -- a browser
User-Agent, `Origin` and `Referer` www.nasdaq.com -- were answered in 1-3 s, so they are sent.
Parsing is defensive: a page whose announcement names no date is a DataError, never a guessed date.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from datetime import datetime
from typing import Any, Mapping

from . import DataError, HttpTransport, read_json, require

HOST = "https://api.nasdaq.com"
SOURCE = "nasdaq"
#: What Nasdaq's own page sends; see the module docstring.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
#: Nasdaq publishes no limit; two seconds between requests is gentle for a page a person refreshes.
MIN_INTERVAL = 2.0
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_ANNOUNCED = re.compile(r"for\s+([A-Z0-9.\-]+)\s*:\s*([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4})")
_NUMERIC = re.compile(r"\bon\s+(\d{1,2}/\d{1,2}/\d{4})")
_ANALYSTS = re.compile(r"based on\s+(\d+)\s+analyst", re.I)
_EPS = re.compile(r"consensus EPS forecast for the quarter is\s+(\(?-?\$?-?\d+(?:\.\d+)?\)?)", re.I)
_LAST_EPS = re.compile(r"reported EPS for the same quarter last year was\s+(\(?-?\$?-?\d+(?:\.\d+)?\)?)", re.I)


def _money(text: str | None) -> float | None:
    if not text:
        return None
    negative = "-" in text or text.startswith("(")
    try:
        value = float(text.replace("$", "").replace("-", "").replace("(", "").replace(")", ""))
    except ValueError:
        return None
    return -value if negative else value


def _date(text: str) -> str | None:
    for pattern in ("%b %d, %Y", "%B %d, %Y", "%b. %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.strip(), pattern).date().isoformat()
        except ValueError:
            continue
    return None


def parse_earnings_date(symbol: str, payload: Any) -> dict[str, Any]:
    """Nasdaq's answer for one symbol as `{symbol, date, estimated, time, eps_forecast, analysts,
    last_year_eps, announcement}`. `estimated` is True when Nasdaq says the date is Zacks' estimate
    from past reporting dates (not the company's own); `time` is `after_close`, `before_open` or None
    when not said. Raises DataError when the page names no date, or names another symbol."""
    data = payload.get("data") if isinstance(payload, Mapping) else None
    require(isinstance(data, Mapping), f"nasdaq earnings date {symbol}: no data")
    announcement = str(data.get("announcement") or "").strip()
    report = " ".join(str(data.get("reportText") or "").split())
    found = _ANNOUNCED.search(announcement)
    day = None
    if found:
        require(found.group(1).upper() == symbol.upper(), f"nasdaq earnings date {symbol}: the page names {found.group(1)}")
        day = _date(found.group(2))
    if day is None:
        numeric = _NUMERIC.search(report)
        day = _date(numeric.group(1)) if numeric else None
    if day is None:
        raise DataError(f"nasdaq earnings date {symbol}: the page names no date ({announcement[:80] or report[:80]!r})")
    lowered = report.lower()
    timing = ("after_close" if "after market close" in lowered or "after the close" in lowered
              else "before_open" if "before market open" in lowered or "before the open" in lowered or "pre-market" in lowered
              else None)
    analysts = _ANALYSTS.search(report)
    return {
        "symbol": symbol.upper(),
        "date": day,
        "estimated": "estimated" in lowered or "algorithm" in lowered,
        "time": timing,
        "eps_forecast": _money((_EPS.search(report) or [None, None])[1]),
        "analysts": int(analysts.group(1)) if analysts else None,
        "last_year_eps": _money((_LAST_EPS.search(report) or [None, None])[1]),
        "announcement": announcement or None,
    }


class Nasdaq:
    """The next earnings date of a stock, as Nasdaq shows it now."""

    source = SOURCE

    def __init__(self, transport: Any = None, *, timeout: float = 20.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=HEADERS["User-Agent"], min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def earnings_date(self, symbol: str) -> dict[str, Any]:
        name = str(symbol or "").strip().upper()
        if not SYMBOL.match(name):
            raise DataError(f"not a stock symbol: {symbol!r}")
        url = f"{HOST}/api/analyst/{urllib.parse.quote(name)}/earnings-date"
        return parse_earnings_date(name, read_json(self.transport, url, headers=dict(HEADERS), timeout=self.timeout,
                                                   what=f"nasdaq earnings date {name}"))


__all__ = ["HEADERS", "HOST", "Nasdaq", "parse_earnings_date"]

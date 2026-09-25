"""The European Central Bank's euro foreign exchange reference rates (Sept 25, 2026, the Kalshi-scale
run's `fx` recorder, league/open_feeds_macro.py).

Kalshi lists daily EUR/USD and USD/JPY ranges (KXEURUSD, KXUSDJPY); the ECB's reference rates are the
key-free, public, point-in-time daily fixing of every major currency against the euro. The ECB
publishes them "around 16:00 CET" on each TARGET business day; the files carry each day's date,
never the minute it appeared, but the server's `Last-Modified` does (Sept 24, 2026: 13:56:26 GMT,
15:56 CEST).

    GET https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml     (the newest day, about 1.5 KB)
    GET https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml  (the last 90 days, about 70 KB)
      <Cube time='2026-09-24'><Cube currency='USD' rate='1.1367'/> ... </Cube>: units of the currency
      per one euro, 30 currencies.

The answer is read with regular expressions, not an XML parser: it is a flat list of attributes,
and no entity in a response is ever expanded.
"""

from __future__ import annotations

import math
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

HOST = "https://www.ecb.europa.eu"
DAILY_URL = HOST + "/stats/eurofxref/eurofxref-daily.xml"
HIST_90D_URL = HOST + "/stats/eurofxref/eurofxref-hist-90d.xml"
#: The ECB's robots.txt asks for five seconds between requests.
MIN_INTERVAL = 5.0
_DAY = re.compile(r"<Cube\s+time=['\"](\d{4}-\d{2}-\d{2})['\"]\s*>(.*?)</Cube>", re.S)
_RATE = re.compile(r"<Cube\s+currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]\s*/>")


def parse_rates(body: "bytes | str") -> dict[str, dict[str, float]]:
    """An ECB reference-rate file as {date: {currency: units per euro}}. A file with no day is a DataError."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    require("eurofxref" in text[:600] or "European Central Bank" in text[:600], "ecb: not the reference-rate file")
    out: dict[str, dict[str, float]] = {}
    for day, block in _DAY.findall(text):
        rates = {}
        for currency, rate in _RATE.findall(block):
            number = float(rate)
            if math.isfinite(number) and number > 0:
                rates[currency] = number
        if rates:
            out[day] = rates
    require(out, "ecb: no reference rates in the file")
    return out


def last_modified(headers: Any) -> float | None:
    """The server's Last-Modified as epoch seconds, or None."""
    value = (headers or {}).get("last-modified") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value)).timestamp()
    except (TypeError, ValueError, IndexError):
        return None


class Ecb:
    """The ECB's daily and 90-day reference-rate files, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _file(self, url: str) -> tuple[dict[str, dict[str, float]], float | None]:
        status, headers, body = self.transport.get(url, {"Accept": "application/xml", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        if status != 200:
            raise DataError(f"ecb: HTTP {status} from {url}")
        return parse_rates(body), last_modified(headers)

    def daily(self) -> tuple[dict[str, dict[str, float]], float | None]:
        """(the newest day's rates, the file's Last-Modified)."""
        return self._file(DAILY_URL)

    def last_90_days(self) -> tuple[dict[str, dict[str, float]], float | None]:
        return self._file(HIST_90D_URL)


__all__ = ["DAILY_URL", "Ecb", "HIST_90D_URL", "HOST", "last_modified", "parse_rates"]

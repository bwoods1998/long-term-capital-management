"""Attention underlyings: Wikipedia pageviews and GDELT's news volume (Sept 25, 2026, the Kalshi-scale
run's `pageviews` and `gdelt` recorders, league/open_feeds.py).

Thirty-five agents had asked for attention underlyings by Sept 24, 2026, and the attention desk trades
series on AI model share (KXANTHSHARE, KXOPENSHARE, KXTOKENUSE), Truth Social posts and what the
president says. Neither host publishes the settlement number of those markets; both publish how much
the world is looking at their subjects, key-free:

    GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<Title>/daily/<YYYYMMDD>/<YYYYMMDD>
      items[]: article, timestamp ("2026092400" = the UTC day 2026-09-24), views (int), granularity,
      access, agent. HTTP 404 {"detail": "... we either do not have data for those date(s) ..."} for a
      title or range with no data. Probed Sept 25, 2026 06:55Z: Sept 24's views were already served.
    GET https://api.gdeltproject.org/api/v2/doc/doc?query=<q>&mode=timelinevolraw&format=json&timespan=1d
      query_details {title, date_resolution: "15m"}, timeline[0]: {series: "Article Count", data[]:
      {date: "20260922T070000Z", value (articles matching), norm (all articles monitored)}} -- a
      bucket with nothing is left out. Answers in 10-15 s; a second request 20 s after the first was
      refused: HTTP 429 "Please limit requests to one every 5 seconds" (probed Sept 25, 2026).

Terms (read Sept 25, 2026): Wikimedia's REST data is CC0 and scripted clients must send an informative
User-Agent with a contact (https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy; the API
usage guidelines allow 200 requests a minute to such a client). GDELT's data is "available for
unlimited and unrestricted use for any academic, commercial, or governmental use of any kind without
fee", with a citation of the GDELT Project and a link REQUIRED (https://www.gdeltproject.org/about.html).
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
from datetime import date, datetime, timezone
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, require

WIKIMEDIA_HOST = "https://wikimedia.org"
PAGEVIEWS_URL = WIKIMEDIA_HOST + "/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
GDELT_HOST = "https://api.gdeltproject.org"
GDELT_DOC_URL = GDELT_HOST + "/api/v2/doc/doc"
#: GDELT's own words, when it refuses: "Please limit requests to one every 5 seconds".
GDELT_SPACING = 6.0
MIN_INTERVAL = 0.5


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def parse_pageviews(payload: Any) -> list[dict[str, Any]]:
    """Wikimedia's per-article daily views as `[{date, views}]`, oldest first."""
    items = payload.get("items") if isinstance(payload, Mapping) else None
    require(isinstance(items, list), "wikimedia pageviews: no items")
    out = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        stamp_text, views = str(item.get("timestamp") or ""), _int(item.get("views"))
        if len(stamp_text) < 8 or not stamp_text[:8].isdigit() or views is None:
            continue
        out.append({"date": f"{stamp_text[:4]}-{stamp_text[4:6]}-{stamp_text[6:8]}", "views": views})
    out.sort(key=lambda row: row["date"])
    return out


def parse_timeline(payload: Any) -> list[dict[str, Any]]:
    """GDELT's volume timeline as `[{t, articles, all_articles, share}]`, oldest first: `share` is the
    matching articles over all articles monitored in the bucket (None when that is zero)."""
    timeline = payload.get("timeline") if isinstance(payload, Mapping) else None
    require(isinstance(timeline, list), "gdelt: no timeline")
    out = []
    for series in timeline:
        for point in (series.get("data") if isinstance(series, Mapping) else None) or []:
            if not isinstance(point, Mapping):
                continue
            try:
                moment = datetime.strptime(str(point.get("date")), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            value, norm = _int(point.get("value")), _int(point.get("norm"))
            if value is None:
                continue
            out.append({"t": moment.strftime("%Y-%m-%dT%H:%M:%SZ"), "articles": value, "all_articles": norm,
                        "share": round(value / norm, 8) if norm else None})
    out.sort(key=lambda row: row["t"])
    return out


class Signals:
    """Wikipedia pageviews and GDELT's news-volume timeline, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _get(self, url: str) -> tuple[int, bytes]:
        status, _, body = self.transport.get(url, {"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        return status, body

    def pageviews(self, title: str, start: date, end: date) -> list[dict[str, Any]]:
        """The article's daily views over [start, end]; [] when Wikimedia has none there (its HTTP 404)."""
        url = f"{PAGEVIEWS_URL}/{urllib.parse.quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
        status, body = self._get(url)
        if status == 404:
            return []
        if status != 200:
            raise DataError(f"wikimedia pageviews: HTTP {status} from {url}")
        try:
            return parse_pageviews(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataError(f"wikimedia pageviews: malformed JSON from {url}") from exc

    def timeline(self, query: str, timespan: str = "1d") -> list[dict[str, Any]]:
        """GDELT's 15-minute volume timeline of `query` over `timespan`."""
        params = {"query": query, "mode": "timelinevolraw", "format": "json", "timespan": timespan}
        url = f"{GDELT_DOC_URL}?{urllib.parse.urlencode(params)}"
        status, body = self._get(url)
        if status == 429:
            raise DataError(f"gdelt: HTTP 429, asked to wait ({body[:80].decode('utf-8', 'replace').strip()})")
        if status != 200:
            raise DataError(f"gdelt: HTTP {status} from {url}")
        try:
            return parse_timeline(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataError(f"gdelt: malformed JSON from {url}") from exc


__all__ = ["GDELT_DOC_URL", "GDELT_SPACING", "PAGEVIEWS_URL", "Signals", "parse_pageviews", "parse_timeline"]

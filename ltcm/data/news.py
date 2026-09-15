"""Headlines from an allowlist of public RSS and Atom feeds.

This module reads *feeds only*. It never fetches an article body: publisher pages are licensed
content, frequently paywalled, and none of it belongs in the floor's context or on the public
site. A desk gets a title, a link, a timestamp and the name of the outlet, and can reason about
what is being said without republishing anyone's copy.

The allowlist is closed. A model-supplied string can pick a symbol or a query, never a host.

  - Yahoo Finance per-symbol headlines
    https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US
  - SEC press releases (RSS on the newsroom at https://www.sec.gov/news/pressreleases)
    https://www.sec.gov/news/pressreleases.rss
  - Google News search results as RSS
    https://news.google.com/rss/search?q=...&hl=en-US&gl=US&ceid=US:en

Both RSS 2.0 (`channel/item`) and Atom (`feed/entry`) are parsed with `xml.etree.ElementTree`
with entity expansion left at its safe default; titles and descriptions are HTML-stripped.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

from . import DataError, HttpTransport, iso, strip_html

YAHOO_HEADLINES = "https://feeds.finance.yahoo.com/rss/2.0/headline"
SEC_PRESS_RELEASES = "https://www.sec.gov/news/pressreleases.rss"
SEC_LITIGATION = "https://www.sec.gov/rss/litigation/litreleases.xml"
GOOGLE_NEWS_SEARCH = "https://news.google.com/rss/search"

#: Only these hosts are ever requested, whatever a desk asks for.
ALLOWED_HOSTS = frozenset(
    {"feeds.finance.yahoo.com", "www.sec.gov", "news.google.com"}
)

ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"

SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,14}$")
MAX_ITEMS = 100
MAX_TITLE = 400


def _check_host(url: str) -> str:
    if not isinstance(url, str) or not url.startswith("https://"):
        raise DataError(f"news: refusing a non-HTTPS feed {url!r}")
    host = urllib.parse.urlsplit(url).netloc.lower()
    if host not in ALLOWED_HOSTS:
        raise DataError(f"news: {host!r} is not on the feed allowlist")
    return url


def yahoo_symbol_feed(symbol: str) -> str:
    """The per-symbol Yahoo Finance headline feed URL."""
    if not isinstance(symbol, str) or not SYMBOL.match(symbol.strip()):
        raise DataError(f"news: not a symbol: {symbol!r}")
    query = urllib.parse.urlencode(
        {"s": symbol.strip().upper(), "region": "US", "lang": "en-US"}
    )
    return f"{YAHOO_HEADLINES}?{query}"


def google_news_feed(query: str) -> str:
    """Google News search results as RSS, restricted to the US English edition."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        raise DataError("news: a 1-200 character query is required")
    params = urllib.parse.urlencode(
        {"q": query.strip(), "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    return f"{GOOGLE_NEWS_SEARCH}?{params}"


def _published(value: Any) -> "str | None":
    """RFC-822 (`Mon, 15 Sep 2026 13:04:05 GMT`) or ISO-8601 to a UTC stamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        return iso(parsedate_to_datetime(raw))
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return iso(raw)
    except DataError:
        return None


def _clean(value: Any, *, limit: int = MAX_TITLE) -> str:
    if not isinstance(value, str):
        return ""
    return strip_html(value).replace("\n", " ").strip()[:limit]


def _text(element: "ET.Element | None") -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def parse_feed(payload: "bytes | str", *, fallback_source: str = "") -> list[dict[str, Any]]:
    """RSS 2.0 or Atom to `[{title, url, published, source}]`, newest-first order preserved.

    Malformed XML raises `DataError`; an individual item missing a title or link is skipped
    rather than guessed at.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise DataError(f"news: malformed feed XML ({exc})") from exc
    tag = root.tag.split("}")[-1].lower()
    if tag == "rss" or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None:
            return []
        channel_title = _clean(_text(channel.find("title")), limit=120)
        items = channel.findall("item")
        return _rss_items(items, channel_title or fallback_source)
    if tag == "feed":
        feed_title = _clean(_text(root.find(ATOM + "title")), limit=120)
        return _atom_entries(root.findall(ATOM + "entry"), feed_title or fallback_source)
    raise DataError(f"news: {tag!r} is neither an RSS channel nor an Atom feed")


def _rss_items(items: "Iterable[ET.Element]", channel_title: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        title = _clean(_text(item.find("title")))
        link = (_text(item.find("link")) or "").strip()
        if not link:
            guid = item.find("guid")
            candidate = (_text(guid) or "").strip()
            if candidate.startswith("http"):
                link = candidate
        if not title or not link.startswith("http"):
            continue
        source_element = item.find("source")
        source = _clean(_text(source_element), limit=120) if source_element is not None else ""
        published = (
            _published(_text(item.find("pubDate")))
            or _published(_text(item.find(DC + "date")))
        )
        rows.append(
            {
                "title": title,
                "url": link,
                "published": published,
                "source": source or channel_title,
            }
        )
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def _atom_entries(entries: "Iterable[ET.Element]", feed_title: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        title = _clean(_text(entry.find(ATOM + "title")))
        link = ""
        for candidate in entry.findall(ATOM + "link"):
            href = (candidate.get("href") or "").strip()
            relation = candidate.get("rel") or "alternate"
            if href.startswith("http") and relation == "alternate":
                link = href
                break
            if href.startswith("http") and not link:
                link = href
        if not title or not link:
            continue
        published = (
            _published(_text(entry.find(ATOM + "published")))
            or _published(_text(entry.find(ATOM + "updated")))
        )
        source_element = entry.find(ATOM + "source")
        source = ""
        if source_element is not None:
            source = _clean(_text(source_element.find(ATOM + "title")), limit=120)
        rows.append(
            {
                "title": title,
                "url": link,
                "published": published,
                "source": source or feed_title,
            }
        )
        if len(rows) >= MAX_ITEMS:
            break
    return rows


class News:
    """Headline reader over the allowlisted feeds. Never fetches an article body."""

    source = "rss"

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 600.0,
    ):
        self.transport = transport or HttpTransport(cache_dir=cache_dir, ttl=cache_ttl)
        self.timeout = float(timeout)

    def feed(self, url: str, *, limit: int = 20, fallback_source: str = "") -> list[dict[str, Any]]:
        """Fetch and parse one allowlisted feed."""
        checked = _check_host(url)
        status, _, body = self.transport.get(
            checked, {"Accept": "application/rss+xml, application/atom+xml, application/xml"},
            self.timeout,
        )
        if status != 200:
            raise DataError(f"news: HTTP {status} from {checked}")
        rows = parse_feed(body, fallback_source=fallback_source)
        capped = max(1, min(int(limit), MAX_ITEMS))
        return rows[:capped]

    def headlines(self, symbol: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Yahoo Finance headlines tagged to one ticker."""
        return self.feed(yahoo_symbol_feed(symbol), limit=limit, fallback_source="Yahoo Finance")

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Google News search results for a free-text query."""
        return self.feed(google_news_feed(query), limit=limit, fallback_source="Google News")

    def sec_press_releases(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """The SEC newsroom feed: enforcement, rulemaking and staff announcements."""
        return self.feed(SEC_PRESS_RELEASES, limit=limit, fallback_source="SEC")


__all__ = [
    "News",
    "parse_feed",
    "yahoo_symbol_feed",
    "google_news_feed",
    "ALLOWED_HOSTS",
    "YAHOO_HEADLINES",
    "SEC_PRESS_RELEASES",
    "GOOGLE_NEWS_SEARCH",
]

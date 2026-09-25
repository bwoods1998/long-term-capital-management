"""Government notices a desk can trade on: the White House's presidential actions, the Federal
Register's presidential documents, and Nasdaq's trading halts (Sept 25, 2026, the Kalshi-scale run's
recorders, league/open_feeds_more.py).

Kalshi's KXTRUMPACT ("Will Trump do anything today?") settles on https://www.whitehouse.gov/presidential-actions/,
and the attention desk trades it; the equity desks trade stocks a halt stops. Each source is key-free
and public; the terms read are named in each recorder's docstring.

    GET https://www.whitehouse.gov/presidential-actions/feed/[?paged=N]
      RSS 2.0 (WordPress): channel/item: title, link, pubDate ("Fri, 18 Sep 2026 22:02:43 +0000": the
      post's publication, UTC, to the second), category (CDATA; "Presidential Actions" on every item
      and one of "Executive Orders", "Proclamations", "Presidential Memoranda", "Nominations &
      Appointments"), guid ("https://www.whitehouse.gov/?p=50541"). Thirty items a page, newest first;
      `paged=2` is the thirty before (Sept 25, 2026: page 1 reached back to Aug 14, page 2 to Jul 13);
      a page past the end answers 404. About 0.6 MB a page (the full text rides along).
    GET https://www.federalregister.gov/api/v1/documents.json?conditions[type][]=PRESDOCU
        &conditions[publication_date][gte]=..&[lte]=..&order=newest&per_page=..&fields[]=..
      count, total_pages, next_page_url, results[]: document_number, title, subtype ("Executive Order",
      "Proclamation", "Memorandum", ...), signing_date, publication_date, executive_order_number,
      proclamation_number, html_url, public_inspection_pdf_url, citation. The API only: the site's
      HTML pages answer automated clients with a CAPTCHA, which the House never touches.
    GET https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts
      RSS 2.0: item: ndaq:HaltDate (MM/DD/YYYY), ndaq:HaltTime (HH:MM:SS.mmm, Eastern), IssueSymbol,
      IssueName, Market, ReasonCode, PauseThresholdPrice, ResumptionDate, ResumptionQuoteTime,
      ResumptionTradeTime (empty until the issue resumes). The day's halts; `ttl` 1 (minute).

Every value in a result is a str, int, float, bool or None so it ships as JSON. XML is read with regular
expressions over a flat structure: no entity in a response is ever expanded beyond the five XML ones.
"""

from __future__ import annotations

import html
import re
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

WHITEHOUSE_FEED_URL = "https://www.whitehouse.gov/presidential-actions/feed/"
FEDERAL_REGISTER_URL = "https://www.federalregister.gov/api/v1/documents.json"
HALTS_URL = "https://www.nasdaqtrader.com/rss.aspx"
NEW_YORK = ZoneInfo("America/New_York")
#: The White House's categories, by the key a strategy names.
ACTION_CATEGORIES = {"executive_orders": "Executive Orders", "proclamations": "Proclamations",
                     "memoranda": "Presidential Memoranda", "nominations": "Nominations & Appointments"}
#: The Federal Register's presidential document subtypes, by key.
DOCUMENT_SUBTYPES = {"executive_orders": "Executive Order", "proclamations": "Proclamation", "memoranda": "Memorandum"}
FR_FIELDS = ("document_number", "title", "subtype", "signing_date", "publication_date", "executive_order_number",
             "proclamation_number", "html_url", "public_inspection_pdf_url", "citation")
#: Between two requests to one host (Nasdaq asks for at most one a minute on its feed; the recorders ask far less).
MIN_INTERVAL = 1.0

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)


def _tag(block: str, name: str) -> str | None:
    found = re.search(rf"<{re.escape(name)}(?:\s[^>]*)?>(.*?)</{re.escape(name)}>", block, re.S)
    if found is None:
        return None
    text = found.group(1).strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        text = text[9:-3]
    return html.unescape(text).strip() or None


def _text(body: "bytes | str") -> str:
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)


def parse_actions(body: "bytes | str") -> list[dict[str, Any]]:
    """The White House feed as [{title, link, guid, published (UTC ISO), published_at (epoch), categories,
    kind}], newest first. Raises DataError unless it is the presidential actions feed."""
    text = _text(body)
    require("<rss" in text[:2000] and "<channel>" in text, "whitehouse: not an RSS feed")
    out = []
    for block in _ITEM.findall(text):
        title, link, published = _tag(block, "title"), _tag(block, "link"), _tag(block, "pubDate")
        if not title or not link or not published:
            continue
        try:
            moment = parsedate_to_datetime(published)
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is None:
            continue
        categories = [html.unescape(c).strip() for c in re.findall(r"<category><!\[CDATA\[(.*?)\]\]></category>", block)]
        kind = next((key for key, name in ACTION_CATEGORIES.items() if name in categories), "other")
        at = moment.timestamp()
        out.append({"title": title, "link": link, "guid": _tag(block, "guid") or link,
                    "published": datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "published_at": at,
                    "categories": [c for c in categories if c != "Presidential Actions"], "kind": kind})
    out.sort(key=lambda row: row["published_at"], reverse=True)
    return out


def parse_documents(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """A Federal Register answer as ([{document_number, title, subtype, signing_date, publication_date,
    executive_order_number, proclamation_number, html_url, public_inspection_url, citation}], next page URL)."""
    require(isinstance(payload, dict) and isinstance(payload.get("results", []), list), "federal register: no results")
    out = []
    for row in payload.get("results") or []:
        if not isinstance(row, dict) or not row.get("document_number") or len(str(row.get("publication_date") or "")) != 10:
            continue
        out.append({"document_number": str(row["document_number"]), "title": str(row.get("title") or ""),
                    "subtype": row.get("subtype"), "signing_date": row.get("signing_date"),
                    "publication_date": str(row["publication_date"]),
                    "executive_order_number": str(row["executive_order_number"]) if row.get("executive_order_number") else None,
                    "proclamation_number": str(row["proclamation_number"]) if row.get("proclamation_number") else None,
                    "html_url": row.get("html_url"), "public_inspection_url": row.get("public_inspection_pdf_url"),
                    "citation": row.get("citation")})
    return out, (str(payload.get("next_page_url")) if payload.get("next_page_url") else None)


def _eastern(day: str, clock: str) -> float | None:
    """MM/DD/YYYY and HH:MM:SS[.mmm] in New York time, as UTC epoch seconds."""
    try:
        moment = datetime.strptime(f"{day.strip()} {clock.strip()[:8]}", "%m/%d/%Y %H:%M:%S")
    except (AttributeError, ValueError):
        return None
    return moment.replace(tzinfo=NEW_YORK).timestamp()


def parse_halts(body: "bytes | str") -> list[dict[str, Any]]:
    """Nasdaq's trade halts feed as [{symbol, name, market, reason, halted (UTC ISO), pause_threshold,
    resumed_quotes, resumed_trading}], oldest halt first. Raises DataError unless it is the halts feed."""
    text = _text(body).lstrip("﻿")
    require("<rss" in text[:500] and "NASDAQ Trade Halts" in text[:2000], "nasdaq halts: not the trade halts feed")
    out = []
    for block in _ITEM.findall(text):
        symbol = _tag(block, "ndaq:IssueSymbol")
        halted = _eastern(_tag(block, "ndaq:HaltDate") or "", _tag(block, "ndaq:HaltTime") or "")
        if not symbol or halted is None:
            continue
        resume_day = _tag(block, "ndaq:ResumptionDate")
        quotes = _eastern(resume_day or "", _tag(block, "ndaq:ResumptionQuoteTime") or "") if resume_day else None
        trading = _eastern(resume_day or "", _tag(block, "ndaq:ResumptionTradeTime") or "") if resume_day else None
        iso = lambda at: datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if at is not None else None  # noqa: E731
        out.append({"symbol": symbol.upper(), "name": _tag(block, "ndaq:IssueName"), "market": _tag(block, "ndaq:Market"),
                    "reason": _tag(block, "ndaq:ReasonCode"), "halted": iso(halted), "pause_threshold": _tag(block, "ndaq:PauseThresholdPrice"),
                    "resumed_quotes": iso(quotes), "resumed_trading": iso(trading)})
    out.sort(key=lambda row: (row["halted"], row["symbol"]))
    return out


class Notices:
    """The White House's actions, the Federal Register's presidential documents and Nasdaq's halts,
    asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 30.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _get(self, url: str, accept: str, what: str) -> tuple[int, bytes]:
        status, _, body = self.transport.get(url, {"Accept": accept, "User-Agent": CONTACT_USER_AGENT}, self.timeout)
        head = body[:3000].lower()
        if status in (403, 429) and (b"captcha" in head or b"challenge" in head or b"unblock" in head):
            from .attention import Blocked

            raise Blocked(f"{what}: the site answered a bot check (HTTP {status}), not the data")
        return status, body

    def actions(self, page: int = 1) -> list[dict[str, Any]]:
        """One page of the White House's presidential actions feed; [] past its last page (HTTP 404)."""
        url = WHITEHOUSE_FEED_URL + (f"?paged={int(page)}" if int(page) > 1 else "")
        status, body = self._get(url, "application/rss+xml", "whitehouse")
        if status == 404 and int(page) > 1:
            return []
        if status != 200:
            raise DataError(f"whitehouse: HTTP {status} from {url}")
        return parse_actions(body)

    def documents(self, since: str, until: str, *, per_page: int = 200, pages: int = 3) -> list[dict[str, Any]]:
        """Presidential documents published from `since` to `until` (YYYY-MM-DD, both inclusive), newest first."""
        params: list[tuple[str, str]] = [("conditions[type][]", "PRESDOCU"), ("conditions[publication_date][gte]", since),
                                         ("conditions[publication_date][lte]", until), ("order", "newest"),
                                         ("per_page", str(int(per_page)))] + [("fields[]", f) for f in FR_FIELDS]
        url: str | None = FEDERAL_REGISTER_URL + "?" + urllib.parse.urlencode(params)
        out: list[dict[str, Any]] = []
        for _ in range(max(1, int(pages))):
            if url is None:
                break
            rows, url = parse_documents(read_json(self.transport, url, headers={"Accept": "application/json",
                                                                                  "User-Agent": CONTACT_USER_AGENT},
                                                  timeout=self.timeout, what="federal register"))
            out.extend(rows)
        if url is not None:
            raise DataError(f"federal register: more than {pages} pages of documents from {since} to {until}; not read to the end")
        return out

    def halts(self) -> list[dict[str, Any]]:
        status, body = self._get(HALTS_URL + "?feed=tradehalts", "application/rss+xml", "nasdaq halts")
        if status != 200:
            raise DataError(f"nasdaq halts: HTTP {status}")
        return parse_halts(body)


__all__ = ["ACTION_CATEGORIES", "DOCUMENT_SUBTYPES", "FEDERAL_REGISTER_URL", "FR_FIELDS", "HALTS_URL", "Notices", "WHITEHOUSE_FEED_URL",
           "parse_actions", "parse_documents", "parse_halts"]

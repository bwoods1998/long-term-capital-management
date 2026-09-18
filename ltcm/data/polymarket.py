"""Polymarket public market data: the Gamma market index and the CLOB book and price history.

Polymarket lists many of the same questions Kalshi does (Fed decisions, elections, sports,
weather), and its CLOB prices are a second opinion on every one of them. A desk that prices a
Kalshi contract against the Polymarket book on the same question has a cross-market anchor that
neither venue's own order flow provides. Nothing here trades; both hosts are keyless and public.

Hosts and endpoints, with the fields relied on (probed live Sept 18, 2026):

    https://gamma-api.polymarket.com
        GET /markets?limit=N&active=true&closed=false&order=volume24hr&ascending=false
            []: id, question, slug, conditionId, endDate, volume24hr (number),
                liquidity (decimal string), outcomes (JSON string of a list),
                outcomePrices (JSON string of a list of decimal strings),
                clobTokenIds (JSON string of a list of token id strings)
        GET /markets/{id}                    -> one market object (404 when unknown)
        GET /markets?slug={slug}             -> a list of 0 or 1 markets
        GET /markets?condition_ids={0x...}   -> a list of 0 or 1 markets
    https://clob.polymarket.com
        GET /book?token_id={token}
            bids[] / asks[]: price, size (decimal strings); last_trade_price; tick_size
        GET /prices-history?market={token}&interval=1d&fidelity=5
            history[]: t (unix seconds), p (probability 0..1)

Gamma has no full-text search parameter that answers reliably, so `search()` and `matches()`
fetch one page of active markets ordered by 24h volume and filter locally on the question
and slug tokens. A page of 100 rows is about 700 KB, well inside the transport's 4 MB cap.
Prices are probabilities in [0, 1] and come back as floats so a result ships as JSON.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from typing import Any, Mapping

from . import DataError, HttpTransport, iso, read_json, require

GAMMA_HOST = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"
USER_AGENT = "ltcm (agent@blakewoods.us)"
SOURCE = "polymarket"

#: Polymarket publishes no public rate limit for these hosts; four requests a second is polite.
MIN_INTERVAL = 0.25
#: How many active markets one search page fetches before the local text filter.
PAGE_SIZE = 100

STOPWORDS = frozenset(
    "will the be a an of in on at to by and or vs for is are does do it this that with from "
    "than more less before after who what which when yes no than into out over under above below "
    "up down any than as its their his her he she they them win wins beat beats".split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: Any) -> list[str]:
    """Lowercase word tokens with the question stopwords dropped; numbers stay (years matter)."""
    return [word for word in _TOKEN.findall(str(text or "").lower()) if word not in STOPWORDS]


def _text(value: Any) -> "str | None":
    return str(value) if isinstance(value, str) and value else None


def _float(value: Any) -> "float | None":
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _json_list(value: Any) -> list:
    """Gamma packs lists as JSON strings (`'["Yes", "No"]'`); accept a real list too."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def market_row(market: Any) -> "dict[str, Any] | None":
    """One Gamma market object reduced to the fields a desk prices with, or None if unusable."""
    if not isinstance(market, Mapping):
        return None
    question = _text(market.get("question"))
    market_id = market.get("id")
    if question is None or market_id is None:
        return None
    outcomes = [str(o) for o in _json_list(market.get("outcomes"))]
    prices = [_float(p) for p in _json_list(market.get("outcomePrices"))]
    return {
        "id": str(market_id),
        "question": question,
        "slug": _text(market.get("slug")),
        "condition_id": _text(market.get("conditionId")),
        "outcomes": outcomes,
        "prices": prices,
        "volume_24h": _float(market.get("volume24hr")),
        "liquidity": _float(market.get("liquidity")),
        "end_date": _text(market.get("endDate")),
        "token_ids": [str(t) for t in _json_list(market.get("clobTokenIds"))],
        "active": bool(market.get("active", True)),
        "closed": bool(market.get("closed", False)),
    }


def yes_price(row: Mapping[str, Any]) -> "float | None":
    """The price of the Yes outcome, or the first outcome when the market has no Yes."""
    outcomes = [str(o).lower() for o in row.get("outcomes") or []]
    prices = row.get("prices") or []
    index = outcomes.index("yes") if "yes" in outcomes else 0
    return prices[index] if index < len(prices) else None


def overlap(query_tokens: "list[str]", row: Mapping[str, Any]) -> float:
    """The fraction of query tokens found in the market's question or slug."""
    if not query_tokens:
        return 0.0
    haystack = set(tokens(row.get("question"))) | set(tokens(str(row.get("slug") or "").replace("-", " ")))
    hits = sum(1 for word in set(query_tokens) if word in haystack)
    return hits / len(set(query_tokens))


class Polymarket:
    """Active markets by text, one market, the CLOB book, and the price path of a token."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 60.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock

    # ------------------------------------------------------------------ reads
    def _get(self, url: str, what: str) -> Any:
        return read_json(
            self.transport,
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=self.timeout,
            what=what,
        )

    def _page(self, limit: int = PAGE_SIZE, active: bool = True) -> list[dict[str, Any]]:
        params = {
            "limit": max(1, min(int(limit), 500)),
            "order": "volume24hr",
            "ascending": "false",
        }
        if active:
            params["active"] = "true"
            params["closed"] = "false"
        url = GAMMA_HOST + "/markets?" + urllib.parse.urlencode(params)
        payload = self._get(url, "polymarket markets")
        require(isinstance(payload, list), "polymarket markets: not a list")
        rows = [row for row in (market_row(m) for m in payload) if row is not None]
        return rows

    # ---------------------------------------------------------------- markets
    def search(self, query: str, limit: int = 20, active: bool = True) -> list[dict[str, Any]]:
        """Active markets whose question or slug shares tokens with `query`, best overlap first.

        An empty query returns the page as Gamma orders it (24h volume, descending)."""
        rows = self._page(PAGE_SIZE, active)
        words = tokens(query)
        if not words:
            return rows[: max(0, int(limit))]
        scored = []
        for index, row in enumerate(rows):
            score = overlap(words, row)
            if score > 0:
                scored.append((-score, index, row))
        scored.sort(key=lambda item: (item[0], item[1]))
        out = []
        for negative, _, row in scored[: max(0, int(limit))]:
            found = dict(row)
            found["score"] = round(-negative, 4)
            out.append(found)
        return out

    def market(self, key: str) -> dict[str, Any]:
        """One market by Gamma id (digits), condition id (`0x...`) or slug."""
        key = str(key or "").strip()
        require(key, "polymarket market: empty key")
        if key.isdigit():
            url = GAMMA_HOST + "/markets/" + key
        elif key.lower().startswith("0x"):
            url = GAMMA_HOST + "/markets?" + urllib.parse.urlencode({"condition_ids": key})
        else:
            url = GAMMA_HOST + "/markets?" + urllib.parse.urlencode({"slug": key})
        payload = self._get(url, f"polymarket market {key}")
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        row = market_row(payload)
        require(row is not None, f"polymarket market {key}: not found")
        return row

    # ------------------------------------------------------------------- clob
    def book(self, token_id: str) -> dict[str, Any]:
        """The CLOB book for one outcome token: bids high to low, asks low to high, mid, spread."""
        url = CLOB_HOST + "/book?" + urllib.parse.urlencode({"token_id": str(token_id)})
        payload = self._get(url, f"polymarket book {token_id}")
        require(isinstance(payload, Mapping), "polymarket book: not an object")
        bids = _levels(payload.get("bids"), reverse=True)
        asks = _levels(payload.get("asks"), reverse=False)
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        both = best_bid is not None and best_ask is not None
        return {
            "token_id": str(token_id),
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": round((best_bid + best_ask) / 2, 4) if both else None,
            "spread": round(best_ask - best_bid, 4) if both else None,
            "last_trade": _float(payload.get("last_trade_price")),
            "tick_size": _float(payload.get("tick_size")),
            "as_of": iso(float(self.clock())),
        }

    def price_history(self, token_id: str, interval: str = "1d", fidelity: int = 5) -> list[dict[str, Any]]:
        """The token's price path: `[{t: unix seconds, p: probability}]`, oldest first."""
        params = {"market": str(token_id), "interval": str(interval), "fidelity": int(fidelity)}
        url = CLOB_HOST + "/prices-history?" + urllib.parse.urlencode(params)
        payload = self._get(url, f"polymarket history {token_id}")
        require(isinstance(payload, Mapping), "polymarket history: not an object")
        rows = payload.get("history")
        out = []
        for point in rows if isinstance(rows, list) else []:
            if not isinstance(point, Mapping):
                continue
            stamp, price = _float(point.get("t")), _float(point.get("p"))
            if stamp is None or price is None:
                continue
            out.append({"t": int(stamp), "p": price})
        out.sort(key=lambda point: point["t"])
        return out

    # ------------------------------------------------------------ cross-market
    def matches(self, title: str, limit: int = 5, rows: "list[dict[str, Any]] | None" = None) -> list[dict[str, Any]]:
        """The active Polymarket markets that best match a Kalshi title, with their Yes price.

        Scores are the fraction of the title's tokens (stopwords dropped) present in the
        question or slug; a row needs at least half of them to count. Pass `rows` to reuse a
        page already fetched."""
        words = tokens(title)
        if not words:
            return []
        candidates = rows if rows is not None else self._page(PAGE_SIZE, True)
        scored = []
        for index, row in enumerate(candidates):
            score = overlap(words, row)
            if score >= 0.5:
                scored.append((-score, -(row.get("volume_24h") or 0.0), index, row))
        scored.sort(key=lambda item: (item[0], item[1], item[2]))
        out = []
        for negative, _, _, row in scored[: max(0, int(limit))]:
            out.append(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "slug": row.get("slug"),
                    "score": round(-negative, 4),
                    "yes_price": yes_price(row),
                    "outcomes": list(row.get("outcomes") or []),
                    "prices": list(row.get("prices") or []),
                    "token_ids": list(row.get("token_ids") or []),
                    "volume_24h": row.get("volume_24h"),
                    "end_date": row.get("end_date"),
                }
            )
        return out


def _levels(rows: Any, *, reverse: bool) -> list[list[float]]:
    out = []
    for level in rows if isinstance(rows, list) else []:
        if not isinstance(level, Mapping):
            continue
        price, size = _float(level.get("price")), _float(level.get("size"))
        if price is None or size is None or size <= 0:
            continue
        out.append([price, size])
    out.sort(key=lambda level: level[0], reverse=reverse)
    return out


__all__ = [
    "CLOB_HOST",
    "GAMMA_HOST",
    "PAGE_SIZE",
    "Polymarket",
    "STOPWORDS",
    "USER_AGENT",
    "market_row",
    "overlap",
    "tokens",
    "yes_price",
]

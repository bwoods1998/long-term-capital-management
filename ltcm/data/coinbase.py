"""Coinbase Advanced Trade public market data: products, order books and candles.

Spot crypto on `api.coinbase.com`. The `/api/v3/brokerage/market/...` family is the *public*
mirror of the authenticated product endpoints and needs no credentials, which is exactly what a
market-data module should use: nothing here ever signs a request. The trading adapter with its
CDP JWT lives in `ltcm/adapters/coinbase.py`.

Endpoints, verified against the Advanced Trade REST reference:

    GET /api/v3/brokerage/market/products
        https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/list-public-products
    GET /api/v3/brokerage/market/products/{product_id}
        https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product
    GET /api/v3/brokerage/market/product_book?product_id=BTC-USD&limit=1
        https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book
    GET /api/v3/brokerage/market/products/{product_id}/candles?start=&end=&granularity=&limit=
        https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles

`/api/v3/brokerage/best_bid_ask` exists but is *authenticated* and has no public `/market/`
form, so `quote()` reads the public product book instead and gets the same touch.

Every numeric field on these endpoints is a JSON **string**; `decimal_or_none` parses it and
nothing here ever sees a float.
"""

from __future__ import annotations

import time
import urllib.parse
from decimal import Decimal
from typing import Any

from ..broker import Instrument, Quote, money
from . import (
    Bar,
    DataError,
    HttpTransport,
    MarketSession,
    decimal_or_none,
    iso,
    read_json,
    require,
    to_datetime,
    us_equity_session,
)

HOST = "https://api.coinbase.com"
PREFIX = "/api/v3/brokerage"
MARKET = PREFIX + "/market"
SOURCE = "coinbase:advanced"

#: `interval` as the rest of the runtime spells it, mapped to Coinbase's granularity enum and
#: the number of seconds one candle covers.
GRANULARITY: dict[str, tuple[str, int]] = {
    "1m": ("ONE_MINUTE", 60),
    "5m": ("FIVE_MINUTE", 300),
    "15m": ("FIFTEEN_MINUTE", 900),
    "30m": ("THIRTY_MINUTE", 1800),
    "1h": ("ONE_HOUR", 3600),
    "60m": ("ONE_HOUR", 3600),
    "2h": ("TWO_HOUR", 7200),
    "4h": ("FOUR_HOUR", 14400),
    "6h": ("SIX_HOUR", 21600),
    "1d": ("ONE_DAY", 86400),
}

#: Coinbase caps one candles request at 350 rows.
MAX_CANDLES = 350
ADV_BARS = 20


def product_id(instrument: "Instrument | str") -> str:
    """`BTC-USD` from an instrument. Accepts `BTC/USD` and `BTCUSD` spellings too."""
    raw = instrument if isinstance(instrument, str) else (
        instrument.market_id or instrument.symbol
    )
    text_value = str(raw or "").strip().upper().replace("/", "-").replace("_", "-")
    if "-" not in text_value and text_value.endswith("USD") and len(text_value) > 3:
        text_value = text_value[:-3] + "-USD"
    parts = text_value.split("-")
    if len(parts) != 2 or not all(1 <= len(part) <= 12 and part.isalnum() for part in parts):
        raise DataError(f"coinbase: not a product id: {raw!r}")
    return text_value


class CoinbaseMarketData:
    """Public Advanced Trade market data. Read-only; no credentials are used or accepted."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 0.0,
        host: str = HOST,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(cache_dir=cache_dir, ttl=cache_ttl)
        self.timeout = float(timeout)
        self.host = host.rstrip("/")
        self.clock = clock

    # ------------------------------------------------------------------- http
    def url(self, path: str, params: "dict[str, Any] | None" = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        query = ""
        if params:
            pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
            if pairs:
                query = "?" + urllib.parse.urlencode(pairs, doseq=True)
        return f"{self.host}{path}{query}"

    def _get(self, path: str, params: "dict[str, Any] | None" = None, *, what: str) -> Any:
        payload = read_json(
            self.transport,
            self.url(path, params),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what=what,
        )
        require(isinstance(payload, dict), f"{what}: response is not an object")
        return payload

    # --------------------------------------------------------------- products
    def products(
        self, *, product_type: "str | None" = "SPOT", limit: "int | None" = None
    ) -> list[dict[str, Any]]:
        """Every tradable product. The response carries `products` and `num_products`."""
        payload = self._get(
            MARKET + "/products",
            {"product_type": product_type, "limit": limit},
            what="coinbase products",
        )
        rows = payload.get("products")
        require(isinstance(rows, list), "coinbase products: no products array")
        return [self.parse_product(row) for row in rows if isinstance(row, dict)]

    def product(self, instrument: "Instrument | str") -> dict[str, Any]:
        """One product. The single-product response is the bare object, with no wrapper key."""
        pid = product_id(instrument)
        payload = self._get(
            f"{MARKET}/products/{urllib.parse.quote(pid)}", what=f"coinbase product {pid}"
        )
        return self.parse_product(payload)

    @staticmethod
    def parse_product(row: dict[str, Any]) -> dict[str, Any]:
        require(isinstance(row, dict), "coinbase product: row is not an object")
        pid = row.get("product_id")
        require(isinstance(pid, str) and pid, "coinbase product: no product_id")
        return {
            "product_id": pid,
            "price": decimal_or_none(row.get("price")),
            "volume_24h": decimal_or_none(row.get("volume_24h")),
            "base_increment": decimal_or_none(row.get("base_increment")),
            "quote_increment": decimal_or_none(row.get("quote_increment")),
            "base_min_size": decimal_or_none(row.get("base_min_size")),
            "quote_min_size": decimal_or_none(row.get("quote_min_size")),
            "base_name": row.get("base_name"),
            "quote_name": row.get("quote_name"),
            "base_currency_id": row.get("base_currency_id"),
            "quote_currency_id": row.get("quote_currency_id"),
            "status": row.get("status"),
            "product_type": row.get("product_type"),
            "trading_disabled": bool(row.get("trading_disabled")),
            "best_bid": decimal_or_none(row.get("best_bid_price") or row.get("best_bid")),
            "best_ask": decimal_or_none(row.get("best_ask_price") or row.get("best_ask")),
        }

    # ------------------------------------------------------------ product book
    def product_book(self, instrument: "Instrument | str", *, limit: int = 1) -> dict[str, Any]:
        """The top of book: `{product_id, bids, asks, time, mid_market, last}` in Decimals."""
        pid = product_id(instrument)
        payload = self._get(
            MARKET + "/product_book",
            {"product_id": pid, "limit": max(1, min(int(limit), 100))},
            what=f"coinbase book {pid}",
        )
        book = payload.get("pricebook")
        require(isinstance(book, dict), f"coinbase book {pid}: no pricebook object")
        return {
            "product_id": book.get("product_id") or pid,
            "bids": _levels(book.get("bids")),
            "asks": _levels(book.get("asks")),
            "time": book.get("time"),
            "last": decimal_or_none(payload.get("last")),
            "mid_market": decimal_or_none(payload.get("mid_market")),
        }

    # ------------------------------------------------------------- MarketData
    def quote(self, instrument: Instrument) -> Quote:
        """Top of book for a crypto pair. Real-time and public, so `delayed=False`."""
        if instrument.asset_class != "crypto":
            raise DataError(f"coinbase quotes only crypto, not {instrument.asset_class!r}")
        book = self.product_book(instrument, limit=1)
        bid = book["bids"][0][0] if book["bids"] else None
        ask = book["asks"][0][0] if book["asks"] else None
        last = book["last"] or book["mid_market"]
        if bid is None and ask is None and last is None:
            raise DataError(f"coinbase {book['product_id']}: book carries no prices")
        stamp = book["time"]
        try:
            as_of = iso(stamp) if stamp else iso(self.clock())
        except DataError:
            as_of = iso(self.clock())
        return Quote(
            instrument=instrument,
            bid=bid if bid and bid > 0 else None,
            ask=ask if ask and ask > 0 else None,
            last=last if last and last > 0 else None,
            as_of=as_of,
            source=SOURCE,
            delayed=False,
        )

    def candles(
        self,
        instrument: "Instrument | str",
        *,
        interval: str = "1d",
        limit: int = 30,
        end: Any = None,
    ) -> list[dict[str, Any]]:
        """Raw candles, oldest first. `start`, `end` and `granularity` are all required."""
        if interval not in GRANULARITY:
            raise DataError(f"coinbase: unsupported interval {interval!r}")
        granularity, seconds = GRANULARITY[interval]
        count = max(1, min(int(limit), MAX_CANDLES))
        finish = int(to_datetime(end if end is not None else self.clock()).timestamp())
        start = finish - seconds * (count + 1)
        pid = product_id(instrument)
        payload = self._get(
            f"{MARKET}/products/{urllib.parse.quote(pid)}/candles",
            {
                "start": str(start),
                "end": str(finish),
                "granularity": granularity,
                "limit": count,
            },
            what=f"coinbase candles {pid}",
        )
        rows = payload.get("candles")
        require(isinstance(rows, list), f"coinbase candles {pid}: no candles array")
        parsed: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            values = {
                name: decimal_or_none(row.get(name))
                for name in ("low", "high", "open", "close", "volume")
            }
            begin = decimal_or_none(row.get("start"))
            if begin is None or any(value is None for value in values.values()):
                continue
            values["start"] = int(begin)
            parsed.append(values)
        parsed.sort(key=lambda candle: candle["start"])
        return parsed

    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list[Bar]:
        """Candles as `Bar`s, oldest first."""
        seconds = GRANULARITY[interval][1] if interval in GRANULARITY else 0
        if not seconds:
            raise DataError(f"coinbase: unsupported interval {interval!r}")
        bars: list[Bar] = []
        for candle in self.candles(instrument, interval=interval, limit=limit):
            try:
                bars.append(
                    Bar(
                        instrument=instrument,
                        start=iso(candle["start"]),
                        end=iso(candle["start"] + seconds),
                        open=candle["open"],
                        high=candle["high"],
                        low=candle["low"],
                        close=candle["close"],
                        volume=candle["volume"],
                    )
                )
            except DataError:
                continue  # an inconsistent candle is dropped, never repaired
        return bars[-max(1, int(limit)):]

    def session(self, day: Any) -> "MarketSession | None":
        """Crypto never closes; the US equity session is returned for scheduling only."""
        return us_equity_session(day)

    def adv_usd(self, instrument: Instrument) -> "Decimal | None":
        """Average daily dollar volume from the last 20 daily candles."""
        try:
            bars = self.bars(instrument, "1d", ADV_BARS)
        except Exception:  # a source failure means 'cannot say', never a crash
            return None
        usable = [bar for bar in bars if bar.volume > 0]
        if not usable:
            return None
        return sum((bar.dollar_volume for bar in usable), money(0)) / len(usable)


def _levels(rows: Any) -> list[tuple[Decimal, Decimal]]:
    """`[{"price": "...", "size": "..."}, ...]` to `[(price, size), ...]` in source order."""
    if not isinstance(rows, list):
        return []
    levels: list[tuple[Decimal, Decimal]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        price = decimal_or_none(row.get("price"))
        size = decimal_or_none(row.get("size"))
        if price is None or size is None or price <= 0:
            continue
        levels.append((price, size))
    return levels


__all__ = [
    "CoinbaseMarketData",
    "product_id",
    "GRANULARITY",
    "HOST",
    "PREFIX",
    "MARKET",
    "SOURCE",
]

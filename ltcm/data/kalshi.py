"""Kalshi public market data: markets, one market, its order book, and events.

Kalshi is a CFTC-designated contract market whose binary contracts settle at $1.00 or $0.00.
This module reads only public market data; the trading adapter with its signed requests lives in
`ltcm/adapters/kalshi.py`.

Host and paths (https://docs.kalshi.com/getting_started/api_environments):

    https://api.elections.kalshi.com/trade-api/v2/markets
    https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}
    https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook
    https://api.elections.kalshi.com/trade-api/v2/markets/orderbooks?tickers=A&tickers=B
    https://api.elections.kalshi.com/trade-api/v2/events

Prices, two ways. The original v2 fields are integer **cents** (`yes_bid`, `yes_ask`,
`last_price`); the fixed-point migration added dollar-denominated decimal strings alongside them
(`yes_bid_dollars`, `orderbook_fp.yes_dollars`, `volume_fp`), which are the only fields that can
express a sub-cent tick
(https://docs.kalshi.com/getting_started/fixed_point_migration). Every reader here prefers the
`*_dollars` / `*_fp` field and falls back to the integer-cent field, so this code is correct on
both shapes and on a market with a finer tick grid than one cent.

Only yes bids and no bids rest on the book; an ask for yes is a bid for no at the complement
(https://docs.kalshi.com/api-reference/market/get-market-orderbook), so
`yes_ask = 1.00 - best no bid`. Orderbook reads carry `use_yes_price=true`, the flag Kalshi
asks new integrations to set (https://docs.kalshi.com/getting_started/order_direction,
"Orderbook pricing convention"): *"The flag defaults to false to preserve the existing
long-standing behavior; new integrations are encouraged to set it."* The REST snapshot this
module reads still arrives in no-leg pricing, so the complement above stands; when Kalshi flips
the default, the no side arrives already on the yes scale and the complement in `parse_book()`
must go with it. The runtime's quotes come from the market row; the one reader of books is a
strategy's `kit.kalshi_orderbooks` (`orderbooks()`, which sends no flag: on Sept 17, 2026 the
batch endpoint answered the same with and without it), so that migration is one function wide.

Legs. An `Instrument` whose `right` is `"no"` names the NO leg of a market, and `quote()`
returns it in NO dollars: `no_bid = 1 - yes_ask`, `no_ask = 1 - yes_bid`, `no_last = 1 - last`.
The risk engine and the simulator therefore price a NO order in the same currency the desk
quotes it in, and only `adapters/kalshi.py` converts back to the YES scale the wire wants.
"""

from __future__ import annotations

import time
import urllib.parse
from decimal import Decimal
from typing import Any, Iterable

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
    us_equity_session,
)

HOST = "https://api.elections.kalshi.com"
PREFIX = "/trade-api/v2"
BASE = HOST + PREFIX
SOURCE = "kalshi"

ONE = Decimal(1)
CENT = Decimal("0.01")
HUNDRED = Decimal(100)

MARKET_STATUSES = ("unopened", "open", "paused", "closed", "settled")
MAX_LIMIT = 1000
#: `GET /markets/orderbooks` refuses a 101st ticker with a 400 (checked Sept 17, 2026).
MAX_ORDERBOOK_TICKERS = 100


def dollars_from_cents(value: Any) -> "Decimal | None":
    """Integer cents to dollars. `40` -> `Decimal('0.40')`. None for anything unusable."""
    parsed = decimal_or_none(value)
    if parsed is None:
        return None
    return parsed / HUNDRED


def cents_from_dollars(value: Any) -> int:
    """Dollars to the integer cents the legacy order fields want. `0.40` -> `40`."""
    parsed = money(value)
    if parsed < 0 or parsed > ONE:
        raise DataError(f"an event contract price must be $0.00-$1.00, got {parsed}")
    cents = (parsed * HUNDRED).quantize(Decimal(1))
    if cents * CENT != parsed:
        raise DataError(f"{parsed} is not a whole number of cents")
    return int(cents)


def price_field(market: dict[str, Any], name: str) -> "Decimal | None":
    """A price in dollars from `{name}_dollars` if present, else from integer-cent `{name}`."""
    fixed = market.get(name + "_dollars")
    if fixed is not None:
        return decimal_or_none(fixed)
    return dollars_from_cents(market.get(name))


def band_field(band: dict[str, Any], name: str) -> "Decimal | None":
    """One edge of a price band in dollars, from `{name}_dollars` if present, else `{name}`.

    Unlike `price_field` this never divides by a hundred: `price_ranges` is documented in
    dollars on both spellings, and guessing cents here would move an order a hundredfold.
    """
    for key in (name + "_dollars", name):
        value = band.get(key)
        if value is not None:
            parsed = decimal_or_none(value)
            if parsed is not None:
                return parsed
    return None


def parse_price_ranges(rows: Any) -> list[dict[str, Decimal]]:
    """`price_ranges` as `[{"start", "end", "step"}, ...]` in dollars, unusable bands dropped.

    *"Valid price ranges for orders on this market"*
    (https://docs.kalshi.com/api-reference/market/get-market). There is no scalar tick size:
    a market can price in centi-cents inside one band and pennies inside another.
    """
    if not isinstance(rows, list):
        return []
    bands: list[dict[str, Decimal]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = band_field(row, "start")
        end = band_field(row, "end")
        step = band_field(row, "step")
        if start is None or end is None or step is None:
            continue
        if step <= 0 or end < start or start < 0 or end > ONE:
            continue
        bands.append({"start": start, "end": end, "step": step})
    bands.sort(key=lambda band: band["start"])
    return bands


def count_field(market: dict[str, Any], name: str) -> "Decimal | None":
    """A contract count from `{name}_fp` if present, else from the integer `{name}`."""
    fixed = market.get(name + "_fp")
    if fixed is not None:
        return decimal_or_none(fixed)
    return decimal_or_none(market.get(name))


def _int_or_none(value: Any) -> "int | None":
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class KalshiMarketData:
    """Public Kalshi market data. Read-only; no credentials are used or accepted."""

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
        """Absolute URL for a `/trade-api/v2`-relative path."""
        if not path.startswith("/"):
            path = "/" + path
        query = ""
        if params:
            pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
            if pairs:
                query = "?" + urllib.parse.urlencode(pairs, doseq=True)
        return f"{self.host}{PREFIX}{path}{query}"

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

    # ---------------------------------------------------------------- markets
    def markets(
        self,
        *,
        event_ticker: "str | None" = None,
        series_ticker: "str | None" = None,
        tickers: "Iterable[str] | None" = None,
        status: "str | None" = None,
        limit: int = 100,
        cursor: "str | None" = None,
        min_close_ts: "int | None" = None,
        max_close_ts: "int | None" = None,
        mve_filter: "str | None" = None,
    ) -> dict[str, Any]:
        """A page of markets: `{"markets": [...], "cursor": "..."}`.

        `mve_filter` is `"exclude"` or `"only"`: Kalshi's multivariate combo markets
        (`KXMVE...`) are thousands of near-empty rows that otherwise fill every page.
        """
        if mve_filter is not None and mve_filter not in ("exclude", "only"):
            raise DataError(f"kalshi: unknown mve_filter {mve_filter!r}")
        if status is not None and status not in MARKET_STATUSES:
            raise DataError(f"kalshi: unknown market status {status!r}")
        params: dict[str, Any] = {
            "limit": max(1, min(int(limit), MAX_LIMIT)),
            "event_ticker": event_ticker,
            "series_ticker": series_ticker,
            "status": status,
            "cursor": cursor,
            "min_close_ts": min_close_ts,
            "max_close_ts": max_close_ts,
            "mve_filter": mve_filter,
        }
        if tickers:
            params["tickers"] = ",".join(str(t).strip().upper() for t in tickers)
        payload = self._get("/markets", params, what="kalshi markets")
        rows = payload.get("markets")
        require(isinstance(rows, list), "kalshi markets: no markets array")
        return {"markets": [self.parse_market(row) for row in rows], "cursor": payload.get("cursor")}

    def market(self, ticker: str) -> dict[str, Any]:
        """One market, unwrapped from its `{"market": {...}}` envelope."""
        payload = self._get(f"/markets/{_ticker(ticker)}", what=f"kalshi market {ticker}")
        row = payload.get("market")
        require(isinstance(row, dict), f"kalshi market {ticker}: no market object")
        return self.parse_market(row)

    def orderbook(self, ticker: str, *, depth: int = 10) -> dict[str, Any]:
        """Best bids on both sides in dollars, plus the derived yes bid/ask.

        Returns `{"ticker", "yes": [(price, count), ...], "no": [...], "yes_bid", "yes_ask"}`
        with every price a `Decimal` in dollars, best level first.
        """
        payload = self._get(
            f"/markets/{_ticker(ticker)}/orderbook",
            {"depth": max(1, min(int(depth), 100)), "use_yes_price": "true"},
            what=f"kalshi orderbook {ticker}",
        )
        book = self.parse_book(ticker, payload)
        return {key: book[key] for key in ("ticker", "yes", "no", "yes_bid", "yes_ask")}

    def orderbooks(self, tickers: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Live books for many markets, `{ticker: book}`, read now and never from the cache.

        Each book is `{"ticker", "yes", "no", "yes_bid", "yes_ask", "no_bid", "no_ask"}`:
        levels as `[(price, count), ...]` in dollars, best level first, and the touch on both
        legs (`yes_ask = 1 - no_bid`, `no_ask = 1 - yes_bid`; `None` when the other side is
        empty). `GET /markets/orderbooks` takes the tickers as a repeated parameter, at most
        `MAX_ORDERBOOK_TICKERS` a call, so a longer list is read in chunks.

        Checked against the live API on Sept 17, 2026: `?tickers=A&tickers=B` returns one book
        per ticker; `?tickers=A,B` returns a single empty book named "A,B"; 101 tickers is a 400
        ("failed on the 'max' tag"); an unknown ticker comes back as an empty book, not an
        error; and each side's levels arrive worst price first (`no_dollars` 0.01, 0.20, 0.86 ...
        0.89 on KXMLBEXTRAS), so they are sorted best-first here. The listing a strategy screens
        with can be minutes old (the sandbox caches it), which is why this read skips the cache.
        """
        wanted: list[str] = []
        for raw in tickers or ():
            ticker = _ticker(raw)
            if ticker not in wanted:
                wanted.append(ticker)
        fresh = _Uncached(self.transport)
        out: dict[str, dict[str, Any]] = {}
        for start in range(0, len(wanted), MAX_ORDERBOOK_TICKERS):
            chunk = wanted[start : start + MAX_ORDERBOOK_TICKERS]
            # A list of pairs, not a dict: urlencode repeats the key once per ticker.
            query = urllib.parse.urlencode([("tickers", ticker) for ticker in chunk])
            payload = read_json(
                fresh,
                f"{self.host}{PREFIX}/markets/orderbooks?{query}",
                headers={"Accept": "application/json"},
                timeout=self.timeout,
                what="kalshi orderbooks",
            )
            require(isinstance(payload, dict), "kalshi orderbooks: response is not an object")
            rows = payload.get("orderbooks")
            require(isinstance(rows, list), "kalshi orderbooks: no orderbooks array")
            asked = set(chunk)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                if ticker in asked:
                    out[ticker] = self.parse_book(ticker, row)
        return out

    @staticmethod
    def parse_book(ticker: str, payload: Any) -> dict[str, Any]:
        """One book object (`orderbook_fp` in dollars, or the legacy integer-cent `orderbook`)."""
        require(isinstance(payload, dict), f"kalshi orderbook {ticker}: not an object")
        fixed = payload.get("orderbook_fp")
        if isinstance(fixed, dict):
            yes = _levels(fixed.get("yes_dollars"), scale=ONE)
            no = _levels(fixed.get("no_dollars"), scale=ONE)
        else:
            book = payload.get("orderbook")
            require(isinstance(book, dict), f"kalshi orderbook {ticker}: no orderbook object")
            yes = _levels(book.get("yes"), scale=CENT)
            no = _levels(book.get("no"), scale=CENT)
        yes_bid = yes[0][0] if yes else None
        no_bid = no[0][0] if no else None
        # The book carries bids only: each leg's ask is the complement of the other leg's bid.
        return {
            "ticker": _ticker(ticker),
            "yes": yes,
            "no": no,
            "yes_bid": yes_bid,
            "yes_ask": _complement(no_bid),
            "no_bid": no_bid,
            "no_ask": _complement(yes_bid),
        }

    def series(self, ticker: str) -> dict[str, Any]:
        """One series (`ticker`, `title`, `category`, `frequency`, ...), unwrapped."""
        payload = self._get(f"/series/{_ticker(ticker)}", what=f"kalshi series {ticker}")
        row = payload.get("series")
        require(isinstance(row, dict), f"kalshi series {ticker}: no series object")
        return row

    def price_ranges(self, ticker: str) -> list[dict[str, Decimal]]:
        """The market's valid order price bands in dollars, or `[]` when it publishes none."""
        return self.market(ticker).get("price_ranges") or []

    def events(
        self,
        *,
        status: "str | None" = None,
        series_ticker: "str | None" = None,
        limit: int = 100,
        cursor: "str | None" = None,
        with_nested_markets: bool = False,
    ) -> dict[str, Any]:
        """A page of events: `{"events": [...], "cursor": "..."}`."""
        if status is not None and status not in ("unopened", "open", "closed", "settled"):
            raise DataError(f"kalshi: unknown event status {status!r}")
        params: dict[str, Any] = {
            "limit": max(1, min(int(limit), 200)),
            "status": status,
            "series_ticker": series_ticker,
            "cursor": cursor,
        }
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        payload = self._get("/events", params, what="kalshi events")
        rows = payload.get("events")
        require(isinstance(rows, list), "kalshi events: no events array")
        return {"events": rows, "cursor": payload.get("cursor")}

    # ---------------------------------------------------------------- parsing
    @staticmethod
    def parse_market(row: Any) -> dict[str, Any]:
        """One market row with every price normalized to dollars and counts to Decimal."""
        require(isinstance(row, dict), "kalshi market: row is not an object")
        ticker = row.get("ticker")
        require(isinstance(ticker, str) and ticker, "kalshi market: no ticker")
        return {
            "ticker": ticker,
            "event_ticker": row.get("event_ticker"),
            "title": row.get("title") or row.get("yes_sub_title"),
            "yes_sub_title": row.get("yes_sub_title"),
            "no_sub_title": row.get("no_sub_title"),
            "status": row.get("status"),
            "result": row.get("result") or None,
            "yes_bid": price_field(row, "yes_bid"),
            "yes_ask": price_field(row, "yes_ask"),
            "no_bid": price_field(row, "no_bid"),
            "no_ask": price_field(row, "no_ask"),
            "last_price": price_field(row, "last_price"),
            "volume": count_field(row, "volume"),
            "volume_24h": count_field(row, "volume_24h"),
            "open_interest": count_field(row, "open_interest"),
            "open_time": row.get("open_time"),
            "close_time": row.get("close_time"),
            "expiration_time": row.get("expected_expiration_time") or row.get("expiration_time"),
            "can_close_early": bool(row.get("can_close_early")),
            "price_ranges": parse_price_ranges(row.get("price_ranges")),
            # What the contract pays on: "greater" pays above floor_strike, "less" below
            # cap_strike, "between" inside both. Strategies price thresholds from these rather
            # than parsing a subtitle.
            "strike_type": row.get("strike_type"),
            "floor_strike": decimal_or_none(row.get("floor_strike")),
            "cap_strike": decimal_or_none(row.get("cap_strike")),
            # The exchange shard the market trades on (Sept 23, 2026): an order on a shard with no
            # collateral fails with `insufficient_shard_balance`, and `league/shards.py` keeps every
            # shard the desks are offered funded. None where the venue does not say.
            "exchange_index": _int_or_none(row.get("exchange_index")),
        }

    # ------------------------------------------------------------- MarketData
    def quote(self, instrument: Instrument) -> Quote:
        """Bid, ask and last in dollars **on the leg the instrument names**.

        A `right="no"` instrument is quoted in NO dollars, which is the price the desk reasons
        about and the price the risk engine must size against: `no_bid = 1 - yes_ask`,
        `no_ask = 1 - yes_bid`, `no_last = 1 - last`. Buying the NO leg at $0.30 and selling
        the YES leg at $0.70 are the same trade, so the two quotes are complements, never
        independent readings.
        """
        if instrument.asset_class != "event":
            raise DataError(f"kalshi quotes only event contracts, not {instrument.asset_class!r}")
        ticker = instrument.market_id or instrument.symbol
        row = self.market(ticker)
        bid, ask, last = row["yes_bid"], row["yes_ask"], row["last_price"]
        if bid is None and ask is None and last is None:
            raise DataError(f"kalshi {ticker}: market carries no prices")
        if str(instrument.right or "").lower() == "no":
            # The complement swaps the sides as well as the scale: the best price to sell NO
            # is the complement of the best price to buy YES.
            bid, ask, last = _complement(ask), _complement(bid), _complement(last)
        return Quote(
            instrument=instrument,
            bid=bid if bid and bid > 0 else None,
            ask=ask if ask and ask > 0 else None,
            last=last if last and last > 0 else None,
            # Kalshi market rows carry no observation timestamp; the read happened now.
            as_of=iso(self.clock()),
            source=SOURCE,
            delayed=False,
        )

    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list[Bar]:
        """Kalshi candlesticks live under a per-series path this module does not read.

        Returning an empty list keeps `MarketData` total: a desk asking an event contract for
        bars gets "no history here", never a wrong series.
        """
        return []

    def session(self, day: Any) -> "MarketSession | None":
        """Kalshi trades continuously; the US equity session is returned for scheduling only."""
        return us_equity_session(day)

    def adv_usd(self, instrument: Instrument) -> "Decimal | None":
        """24-hour traded value in dollars: contracts times the last price."""
        try:
            row = self.market(instrument.market_id or instrument.symbol)
        except Exception:  # a source failure means 'cannot say', never a crash
            return None
        volume = row.get("volume_24h") or row.get("volume")
        price = row.get("last_price")
        if volume is None or price is None:
            return None
        return volume * price


def _complement(value: "Decimal | None") -> "Decimal | None":
    """`1 - p` for a price that is there, `None` for one that is not."""
    return None if value is None else ONE - value


class _Uncached:
    """A transport view whose GET goes to the network even when the transport caches.

    The sandbox's transport keeps responses for 300 seconds, which suits a market listing and
    not a book an order is about to be priced from. A transport without `request` (a test
    double) is read through its own `get`."""

    def __init__(self, transport: Any):
        self.transport = transport

    def get(self, url: str, headers: "dict[str, str] | None" = None, timeout: Any = None) -> Any:
        request = getattr(self.transport, "request", None)
        if callable(request):
            return request("GET", url, headers=headers, timeout=timeout)
        return self.transport.get(url, headers, timeout)


def _ticker(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw or not all(ch.isalnum() or ch in "-._" for ch in raw):
        raise DataError(f"kalshi: not a market ticker: {value!r}")
    return raw


def _levels(rows: Any, *, scale: Decimal) -> list[tuple[Decimal, Decimal]]:
    """`[[price, count], ...]` to `[(dollars, count), ...]`, best level first.

    Kalshi returns its book worst-to-best on each side, so the list is reversed here and the
    caller can always read index 0 as the touch.
    """
    if not isinstance(rows, list):
        return []
    levels: list[tuple[Decimal, Decimal]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        price = decimal_or_none(row[0])
        count = decimal_or_none(row[1])
        if price is None or count is None or price <= 0:
            continue
        levels.append((price * scale, count))
    levels.sort(key=lambda level: level[0], reverse=True)
    return levels


__all__ = [
    "KalshiMarketData",
    "HOST",
    "PREFIX",
    "BASE",
    "SOURCE",
    "MAX_ORDERBOOK_TICKERS",
    "dollars_from_cents",
    "cents_from_dollars",
    "price_field",
    "count_field",
    "band_field",
    "parse_price_ranges",
]

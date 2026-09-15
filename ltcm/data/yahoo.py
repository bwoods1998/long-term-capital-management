"""Delayed US equity quotes and OHLCV bars from Yahoo Finance's public chart endpoint.

Yahoo is a third-party, explicitly delayed source. Every `Quote` this module returns carries
`delayed=True` and `source="yahoo:delayed"`, so the publisher can label it and never present it
as an exchange feed. Nothing here is a real-time licensed quote and nothing here is republished
as one.

Endpoint (the same one `portfolio_runtime/market.py` has used in production):

    https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}

Response shape, parsed strictly:

    {"chart": {"result": [{"meta": {"symbol", "currency", "regularMarketPrice",
                                    "regularMarketTime", "previousClose", ...},
                           "timestamp": [unix seconds, ...],
                           "indicators": {"quote": [{"open": [], "high": [], "low": [],
                                                     "close": [], "volume": []}],
                                          "adjclose": [{"adjclose": []}]}}],
               "error": null}}

Any missing key, a non-null `chart.error`, a short array or a non-integer timestamp is a
`DataError`: this module never guesses a price.
"""

from __future__ import annotations

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
    us_equity_session,
)

HOST = "https://query2.finance.yahoo.com"
CHART = HOST + "/v8/finance/chart/"
SOURCE = "yahoo:delayed"

#: Yahoo's own interval vocabulary. `bars()` refuses anything else rather than silently
#: substituting a granularity the caller did not ask for.
INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")
INTRADAY = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h")
#: Hourly and coarser intraday granularities are not subject to the sixty-day window.
LONG_INTRADAY = ("60m", "90m", "1h")

#: Calendar ranges Yahoo accepts, smallest first, with the rough number of *sessions* each
#: covers. `bars()` asks for the smallest range that can hold `limit` bars.
DAY_RANGES: tuple[tuple[str, int], ...] = (
    ("5d", 5),
    ("1mo", 21),
    ("3mo", 63),
    ("6mo", 126),
    ("1y", 252),
    ("2y", 504),
    ("5y", 1260),
    ("10y", 2520),
    ("max", 1_000_000),
)

#: Yahoo caps intraday history per request: one-minute bars reach back eight days ("Only 8 days
#: worth of 1m granularity data are allowed to be fetched per request"), and the 2m-90m band must
#: fall inside the last sixty. Asking for a wider range is a 400, so the tables differ.
MINUTE_RANGES: tuple[tuple[str, int], ...] = (("1d", 1), ("5d", 5))
INTRADAY_RANGES: tuple[tuple[str, int], ...] = (("1d", 1), ("5d", 5), ("1mo", 21), ("3mo", 42))

#: Roughly how many bars one regular session holds at each intraday granularity (390 minutes).
BARS_PER_SESSION = {
    "1m": 390,
    "2m": 195,
    "5m": 78,
    "15m": 26,
    "30m": 13,
    "60m": 7,
    "90m": 5,
    "1h": 7,
}

ADV_BARS = 20
MAX_LIMIT = 5000


def _range_for(interval: str, limit: int) -> str:
    """The smallest Yahoo `range` that can hold `limit` bars at `interval`."""
    if interval in INTRADAY:
        per_session = BARS_PER_SESSION.get(interval, 7)
        sessions = max(1, -(-limit // per_session))
        if interval == "1m":
            table: tuple[tuple[str, int], ...] = MINUTE_RANGES
        elif interval in LONG_INTRADAY:
            table = DAY_RANGES
        else:
            table = INTRADAY_RANGES
    elif interval == "1wk":
        sessions, table = limit * 5, DAY_RANGES
    elif interval in ("1mo", "3mo"):
        sessions, table = limit * 21 * (3 if interval == "3mo" else 1), DAY_RANGES
    else:  # "1d", "5d"
        sessions, table = limit * (5 if interval == "5d" else 1), DAY_RANGES
    for name, capacity in table:
        if capacity >= sessions:
            return name
    return table[-1][0]


def chart_url(symbol: str, *, interval: str, range_: str) -> str:
    """The exact URL fetched. Kept public so tests and receipts can name it."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise DataError("a Yahoo symbol is required")
    query = urllib.parse.urlencode({"range": range_, "interval": interval, "includePrePost": "false"})
    return f"{CHART}{urllib.parse.quote(symbol.strip(), safe='^.=-')}?{query}"


def _result(payload: Any, symbol: str) -> dict[str, Any]:
    """The single `chart.result[0]` object, or a `DataError` explaining what was missing."""
    require(isinstance(payload, dict), f"yahoo {symbol}: response is not an object")
    chart = payload.get("chart")
    require(isinstance(chart, dict), f"yahoo {symbol}: no chart object")
    error = chart.get("error")
    if error:
        code = error.get("code") if isinstance(error, dict) else error
        raise DataError(f"yahoo {symbol}: chart error {code!r}")
    results = chart.get("result")
    require(
        isinstance(results, list) and results and isinstance(results[0], dict),
        f"yahoo {symbol}: chart.result is empty",
    )
    return results[0]


def _epoch(value: Any, symbol: str) -> str:
    """Yahoo timestamps are integer Unix seconds; a float or string is a shape change."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataError(f"yahoo {symbol}: timestamp {value!r} is not integer Unix seconds")
    if value < 0:
        raise DataError(f"yahoo {symbol}: negative timestamp {value}")
    return iso(value)


class YahooMarketData:
    """`MarketData` over Yahoo's chart endpoint. Delayed, public, never a licensed feed."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 0.0,
    ):
        self.transport = transport or HttpTransport(cache_dir=cache_dir, ttl=cache_ttl)
        self.timeout = float(timeout)

    # ------------------------------------------------------------------ fetch
    def _chart(self, symbol: str, *, interval: str, range_: str) -> dict[str, Any]:
        url = chart_url(symbol, interval=interval, range_=range_)
        payload = read_json(
            self.transport,
            url,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what=f"yahoo {symbol}",
        )
        return _result(payload, symbol)

    # ------------------------------------------------------------------ quote
    def quote(self, instrument: Instrument) -> Quote:
        """The delayed last trade, with bid/ask only when Yahoo actually reports them."""
        symbol = instrument.symbol
        result = self._chart(symbol, interval="1d", range_="1d")
        meta = result.get("meta")
        require(isinstance(meta, dict), f"yahoo {symbol}: no meta block")
        last = decimal_or_none(meta.get("regularMarketPrice"))
        if last is None:
            last = decimal_or_none(meta.get("previousClose"))
        if last is None or last <= 0:
            raise DataError(f"yahoo {symbol}: no usable regularMarketPrice")
        stamp_value = meta.get("regularMarketTime")
        as_of = _epoch(stamp_value, symbol) if stamp_value is not None else iso(0)
        bid = decimal_or_none(meta.get("bid"))
        ask = decimal_or_none(meta.get("ask"))
        return Quote(
            instrument=instrument,
            bid=bid if bid and bid > 0 else None,
            ask=ask if ask and ask > 0 else None,
            last=last,
            as_of=as_of,
            source=SOURCE,
            delayed=True,
        )

    # ------------------------------------------------------------------- bars
    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list[Bar]:
        """The most recent `limit` complete bars, oldest first. Incomplete rows are dropped."""
        if interval not in INTERVALS:
            raise DataError(f"yahoo: unsupported interval {interval!r}")
        limit = int(limit)
        if not 1 <= limit <= MAX_LIMIT:
            raise DataError(f"yahoo: limit must be 1..{MAX_LIMIT}")
        symbol = instrument.symbol
        result = self._chart(symbol, interval=interval, range_=_range_for(interval, limit))
        return self._parse_bars(result, instrument, interval)[-limit:]

    @staticmethod
    def _parse_bars(result: dict[str, Any], instrument: Instrument, interval: str) -> list[Bar]:
        symbol = instrument.symbol
        stamps = result.get("timestamp")
        if stamps is None:  # a symbol with no history in the window
            return []
        require(isinstance(stamps, list), f"yahoo {symbol}: timestamp is not a list")
        indicators = result.get("indicators")
        require(isinstance(indicators, dict), f"yahoo {symbol}: no indicators block")
        quotes = indicators.get("quote")
        require(
            isinstance(quotes, list) and quotes and isinstance(quotes[0], dict),
            f"yahoo {symbol}: no indicators.quote block",
        )
        series = quotes[0]
        columns = {}
        for name in ("open", "high", "low", "close", "volume"):
            column = series.get(name)
            require(isinstance(column, list), f"yahoo {symbol}: indicators.quote[0].{name} missing")
            require(
                len(column) == len(stamps),
                f"yahoo {symbol}: {name} has {len(column)} values for {len(stamps)} timestamps",
            )
            columns[name] = column
        seconds = _interval_seconds(interval)
        bars: list[Bar] = []
        for index, stamp in enumerate(stamps):
            values = {name: decimal_or_none(columns[name][index]) for name in columns}
            if any(value is None for value in values.values()):
                continue  # Yahoo pads holidays and halts with nulls; a partial bar is no bar
            if min(values["open"], values["high"], values["low"], values["close"]) <= 0:
                continue
            start = _epoch(stamp, symbol)
            try:
                bars.append(
                    Bar(
                        instrument=instrument,
                        start=start,
                        end=iso(stamp + seconds),
                        open=values["open"],
                        high=values["high"],
                        low=values["low"],
                        close=values["close"],
                        volume=values["volume"],
                    )
                )
            except DataError:
                continue  # an internally inconsistent row (low > close) is dropped, not guessed
        return bars

    # ---------------------------------------------------------------- session
    def session(self, day: Any) -> "MarketSession | None":
        """The US equity session for a day; the calendar is local, not fetched from Yahoo."""
        return us_equity_session(day)

    # -------------------------------------------------------------------- adv
    def adv_usd(self, instrument: Instrument) -> "Decimal | None":
        """Average daily dollar volume over the last 20 complete daily bars."""
        try:
            bars = self.bars(instrument, "1d", ADV_BARS)
        except Exception:  # a source failure means 'cannot say', never a crash
            return None
        usable = [bar for bar in bars if bar.volume > 0]
        if not usable:
            return None
        total = sum((bar.dollar_volume for bar in usable), money(0))
        return total / len(usable)


def _interval_seconds(interval: str) -> int:
    table = {
        "1m": 60,
        "2m": 120,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "60m": 3600,
        "90m": 5400,
        "1h": 3600,
        "1d": 86400,
        "5d": 5 * 86400,
        "1wk": 7 * 86400,
        "1mo": 30 * 86400,
        "3mo": 91 * 86400,
    }
    return table[interval]


__all__ = [
    "YahooMarketData",
    "chart_url",
    "CHART",
    "SOURCE",
    "INTERVALS",
    "ADV_BARS",
    "MINUTE_RANGES",
    "INTRADAY_RANGES",
    "DAY_RANGES",
]

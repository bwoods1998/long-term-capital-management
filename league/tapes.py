"""Tapes: the recorded history the replay simulator walks, and the live snapshots of the same shape.

A strategy sees `bars` and `quotes` (Alpaca) or `markets` (Kalshi) in its `ctx` (`CONTRACT.md`).
This module builds both views of each venue from one set of parsers, so what a strategy is shown
in replay has the shape of what it is shown live:

    AlpacaData(client).bars(...)      live closed bars        AlpacaData(client).tape(...)   history
    AlpacaData(client).quotes(...)    live touch
    KalshiData(md).markets(...)       live open markets       KalshiData(md, history).tape(...)

The tape:

    {"venue": "alpaca" | "kalshi", "horizon": "hour" | "day", "step_seconds": 300,
     "half_spread_bps": 2.0,                       # alpaca only
     "steps": [...],                               # oldest first, strictly increasing "t"
     "results": {"<market>": "yes" | "no"}}        # kalshi only

    alpaca step  {"t": "2026-09-10T13:35:00Z", "bars": {"BTC/USD": {"o", "h", "l", "c", "v"}}}
    kalshi step  {"t": "...", "markets": [{"market", "series", "title", "yes_bid", "yes_ask",
                  "yes_ask_low", "yes_bid_high", "close_time", "hours_to_close", "volume_24h",
                  "open_interest", "strike"}]}

Three rules keep a tape honest.

1. **A bar is stamped with the moment it closed.** Alpaca stamps a bar with its open time; a
   strategy woken at 13:35 may read the 13:30 bar only once it is complete, so `t` here is the
   bar's time plus its timeframe, and a bar that has not closed is never returned.
2. **A Kalshi row carries only what was on the screen at `t`.** The touch is the close of the
   last one-minute candlestick at or before `t` (Kalshi's candles are sparse: a minute in which
   nothing changed has none, so the last one is carried forward), and `yes_ask_low` /
   `yes_bid_high` are the extremes of the touch inside `(t - step, t]`, which is what the
   simulator judges a resting order against. A row is shown only while the book is two-sided and
   the market is still open, exactly as `markets()` shows it live.
3. **Nothing known only after the close picks a market.** When `max_markets` cuts a tape down,
   whole events are taken in a seeded order that depends on the tickers alone: never on volume,
   open interest or the result (Sept 16, 2026: ranked by volume, a capped board kept the winners).

All Alpaca HTTP goes through the project's gateway by way of `ltcm.adapters.VenueClient`; all
Kalshi history goes through `ltcm.history.History` (public API, disk cache, throttle). Standard
library only. Every number in a tape is a float except `step_seconds`.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

DATA_URL = "https://data.alpaca.markets"
CRYPTO_BARS_PATH = "/v1beta3/crypto/us/bars"
CRYPTO_QUOTES_PATH = "/v1beta3/crypto/us/latest/quotes"
STOCK_BARS_PATH = "/v2/stocks/bars"
STOCK_QUOTES_PATH = "/v2/stocks/quotes/latest"

TIMEFRAME_SECONDS = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400}
HORIZONS = ("hour", "day")
DAY = 86400

#: Alpaca's largest page, and how many of them one read will follow before it gives up.
PAGE_LIMIT = 10_000
MAX_PAGES = 60
#: How far back `bars()` reaches when no start is given. Thirty days for the minute timeframes;
#: the hourly and daily ones need longer or `limit` could never be met (30 days is 21 daily bars).
MAX_LOOKBACK_SECONDS = {"1Min": 30 * DAY, "5Min": 30 * DAY, "15Min": 30 * DAY, "1Hour": 180 * DAY, "1Day": 800 * DAY}

#: Pages of open markets read per series for a live snapshot (1,000 rows a page).
MAX_MARKET_PAGES = 10
#: One-minute candles are read from this long before a tape starts, so the first step has a
#: touch to carry forward and `volume_24h` has its day.
CANDLE_WARMUP_SECONDS = DAY

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9./]{0,19}$")
_SERIES = re.compile(r"^[A-Z0-9][A-Z0-9._]{0,39}$")
_STRIKE = re.compile(r"-[TB](-?\d+(?:\.\d+)?)$")


class TapeError(RuntimeError):
    """A tape or a snapshot could not be built: a bad argument, or the venue did not answer."""


# --------------------------------------------------------------------- helpers

def is_crypto(symbol: str) -> bool:
    """Alpaca names a crypto pair `BTC/USD` and an equity `SPY`."""
    return "/" in str(symbol)


def parse_time(value: Any) -> float:
    """An ISO-8601 stamp (a bare one is UTC) or epoch seconds, as epoch seconds."""
    if isinstance(value, bool) or value is None:
        raise TapeError(f"not a time: {value!r}")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise TapeError(f"not a time: {value!r}")
        return float(value)
    raw = str(value).strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    # Alpaca quotes carry nanoseconds; `fromisoformat` reads at most six fractional digits.
    raw = re.sub(r"(\.\d{6})\d+", r"\1", raw)
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise TapeError(f"not a time: {value!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def iso(ts: float) -> str:
    """Epoch seconds as `2026-09-10T13:35:00Z`."""
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _float(value: Any) -> "float | None":
    """A venue number (Decimal, int, str) as a finite float, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, ArithmeticError):
        return None
    return out if math.isfinite(out) else None


def _horizon(value: str) -> str:
    if value not in HORIZONS:
        raise TapeError(f"horizon must be one of {HORIZONS}, got {value!r}")
    return value


def _detail(payload: Any) -> str:
    """A short error text from a venue body."""
    if isinstance(payload, dict):
        for key in ("message", "error", "detail", "msg"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:200]
    if isinstance(payload, str):
        return payload.strip()[:200]
    return ""


def parse_strike(ticker: Any, row: "dict[str, Any] | None" = None) -> "float | None":
    """The strike a market pays on: the ticker's suffix (`-T80999.99` -> 80999.99, `-B81250` ->
    81250.0), else the row's `floor_strike`, else its `cap_strike`; None when there is none."""
    match = _STRIKE.search(str(ticker or "").strip().upper())
    if match:
        return _float(match.group(1))
    for key in ("floor_strike", "cap_strike"):
        value = _float((row or {}).get(key))
        if value is not None:
            return value
    return None


def two_sided(bid: "float | None", ask: "float | None") -> bool:
    """A Kalshi touch someone can trade both ways: a bid above $0, an ask below $1, not crossed.
    An empty side arrives as a $0.00 bid or a $1.00 ask."""
    return bid is not None and ask is not None and 0.0 < bid <= ask < 1.0


# ---------------------------------------------------------------------- alpaca

class AlpacaData:
    """Alpaca bars and quotes through the gateway, for the live `ctx` and for tapes.

    `client` is a `ltcm.adapters.VenueClient` in gateway mode (venue `alpaca-paper` or `alpaca`;
    market data is one host for both) or anything with the same
    `request(method, url, *, headers=None, body=None, what="venue") -> (status, payload)`.
    """

    def __init__(self, client: Any, *, feed: str = "iex", clock: Callable[[], float] = time.time, max_pages: int = MAX_PAGES):
        self.client = client
        self.feed = str(feed)
        self.clock = clock
        self.max_pages = max(1, int(max_pages))

    # -------------------------------------------------------------------- http
    @staticmethod
    def url(path: str, params: "dict[str, Any]") -> str:
        """A data URL. `/`, `,` and `:` stay readable in the query (`symbols=BTC/USD,ETH/USD`)."""
        pairs = [(key, value) for key, value in params.items() if value is not None and value != ""]
        return f"{DATA_URL}{path}?" + urllib.parse.urlencode(pairs, safe="/,:")

    def _get(self, url: str, *, what: str) -> "dict[str, Any]":
        try:
            status, payload = self.client.request("GET", url, headers={}, what=what)
        except TapeError:
            raise
        except Exception as exc:  # a transport failure or a malformed body: one error type out
            raise TapeError(f"{what}: {type(exc).__name__}: {exc}") from exc
        if status != 200:
            detail = _detail(payload)
            raise TapeError(f"{what}: HTTP {status}{(' ' + detail) if detail else ''}")
        if not isinstance(payload, dict):
            raise TapeError(f"{what}: the response is not an object")
        return payload

    @staticmethod
    def _symbols(symbols: Iterable[str]) -> "list[str]":
        if isinstance(symbols, str):
            symbols = [symbols]
        out: list[str] = []
        for raw in symbols or ():
            symbol = str(raw or "").strip().upper()
            if not _SYMBOL.match(symbol):
                raise TapeError(f"not an Alpaca symbol: {raw!r}")
            if symbol not in out:
                out.append(symbol)
        return out

    @staticmethod
    def _timeframe(timeframe: str) -> int:
        seconds = TIMEFRAME_SECONDS.get(timeframe)
        if not seconds:
            raise TapeError(f"timeframe must be one of {sorted(TIMEFRAME_SECONDS)}, got {timeframe!r}")
        return seconds

    # -------------------------------------------------------------------- bars
    def _closed_bars(
        self, symbols: "list[str]", timeframe: str, start_ts: float, end_ts: float, now: float
    ) -> "dict[str, list[dict[str, Any]]]":
        """Every bar of one asset class that closed in [start_ts, min(end_ts, now)], by symbol."""
        seconds = self._timeframe(timeframe)
        crypto = is_crypto(symbols[0])
        what = f"alpaca {'crypto' if crypto else 'stock'} bars"
        last = min(float(end_ts), float(now))
        found: dict[str, dict[int, dict[str, Any]]] = {symbol: {} for symbol in symbols}
        token = None
        for _ in range(self.max_pages):
            params: dict[str, Any] = {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                # A bar is stamped with its open: the one closing at `start` opened a bar earlier.
                "start": iso(start_ts - seconds),
                "end": iso(end_ts),
                "limit": PAGE_LIMIT,
            }
            if not crypto:
                params["feed"] = self.feed
                params["adjustment"] = "all"
            if token:
                params["page_token"] = token
            payload = self._get(self.url(CRYPTO_BARS_PATH if crypto else STOCK_BARS_PATH, params), what=what)
            pages = payload.get("bars")
            if pages is not None and not isinstance(pages, dict):
                raise TapeError(f"{what}: bars is not an object")
            for symbol, rows in (pages or {}).items():
                name = str(symbol).upper()
                if name not in found or not isinstance(rows, list):
                    continue
                for row in rows:
                    bar = self._bar(row, seconds)
                    if bar is not None and start_ts <= bar[0] <= last:
                        found[name][int(bar[0])] = bar[1]
            token = payload.get("next_page_token")
            if not token:
                break
        else:
            raise TapeError(f"{what}: more than {self.max_pages} pages; ask for a shorter window")
        return {symbol: [rows[key] for key in sorted(rows)] for symbol, rows in found.items()}

    @staticmethod
    def _bar(row: Any, seconds: int) -> "tuple[float, dict[str, Any]] | None":
        """One venue bar as (close time, bar stamped with its close); None when unusable."""
        if not isinstance(row, dict):
            return None
        try:
            closed = parse_time(row.get("t")) + seconds
        except TapeError:
            return None
        o, h, l, c = (_float(row.get(key)) for key in ("o", "h", "l", "c"))
        if o is None or h is None or l is None or c is None or min(o, h, l, c) <= 0:
            return None
        volume = _float(row.get("v"))
        return closed, {"t": iso(closed), "o": o, "h": h, "l": l, "c": c, "v": max(0.0, volume or 0.0)}

    @staticmethod
    def default_lookback(timeframe: str, limit: int, *, crypto: bool) -> float:
        """How far back to read for the `limit` most recent closed bars.

        Crypto trades around the clock but a quiet bar is simply absent, so twice the span plus
        an hour. An equity trades 6.5 hours of 24, five days of seven (a fifth of the week), so
        six times the span covers the closed hours and four more days cover a long weekend;
        three times the span alone cannot fill `limit` even on plain weekdays (24 / 6.5 = 3.7)."""
        seconds = TIMEFRAME_SECONDS[timeframe]
        span = float(limit) * seconds
        if crypto:
            reach = span * 2 + 3600
        elif timeframe == "1Day":
            reach = span * 1.5 + 5 * DAY
        else:
            reach = span * 6 + 4 * DAY
        return min(reach, float(MAX_LOOKBACK_SECONDS[timeframe]))

    def bars(
        self,
        symbols: "list[str]",
        timeframe: str,
        *,
        start: "str | None" = None,
        end: "str | None" = None,
        limit: int = 120,
    ) -> "dict[str, list[dict[str, Any]]]":
        """Closed bars by symbol, oldest first: `{"t" (close time), "o", "h", "l", "c", "v"}`.

        `start` and `end` bound the close time, both inclusive; `end` defaults to now and never
        passes it. Without `start`, the `limit` most recent closed bars of each symbol. Crypto
        and equity symbols may be mixed: each class is one (paged) request. Every symbol asked
        for is a key, with an empty list when the venue has no bars for it."""
        names = self._symbols(symbols)
        self._timeframe(timeframe)
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise TapeError(f"limit must be a whole number, got {limit!r}") from exc
        if limit < 1:
            raise TapeError(f"limit must be at least 1, got {limit}")
        now = float(self.clock())
        end_ts = now if end is None else min(parse_time(end), now)
        out: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
        for crypto in (True, False):
            group = [name for name in names if is_crypto(name) == crypto]
            if not group:
                continue
            if start is None:
                start_ts = end_ts - self.default_lookback(timeframe, limit, crypto=crypto)
            else:
                start_ts = parse_time(start)
            if start_ts > end_ts:
                continue
            for name, rows in self._closed_bars(group, timeframe, start_ts, end_ts, now).items():
                out[name] = rows[-limit:] if start is None else rows
        return out

    # ------------------------------------------------------------------ quotes
    def quotes(self, symbols: "list[str]") -> "dict[str, dict[str, float]]":
        """The touch by symbol, `{"BTC/USD": {"bid": .., "ask": ..}}`. A symbol with no two-sided
        quote (a side missing or zero, or the quote crossed) is left out."""
        names = self._symbols(symbols)
        out: dict[str, dict[str, float]] = {}
        for crypto in (True, False):
            group = [name for name in names if is_crypto(name) == crypto]
            if not group:
                continue
            params: dict[str, Any] = {"symbols": ",".join(group)}
            if not crypto:
                params["feed"] = self.feed
            what = f"alpaca {'crypto' if crypto else 'stock'} quotes"
            payload = self._get(self.url(CRYPTO_QUOTES_PATH if crypto else STOCK_QUOTES_PATH, params), what=what)
            rows = payload.get("quotes")
            if not isinstance(rows, dict):
                continue
            for symbol, row in rows.items():
                name = str(symbol).upper()
                if name not in group or not isinstance(row, dict):
                    continue
                bid, ask = _float(row.get("bp")), _float(row.get("ap"))
                if bid is not None and ask is not None and 0.0 < bid <= ask:
                    out[name] = {"bid": bid, "ask": ask}
        return {name: out[name] for name in names if name in out}

    # -------------------------------------------------------------------- tape
    def tape(
        self,
        symbols: "list[str]",
        timeframe: str,
        *,
        start: str,
        end: str,
        horizon: str = "hour",
        half_spread_bps: "float | None" = None,
    ) -> "dict[str, Any]":
        """A replay tape: one step per distinct bar close in [start, end] across the symbols. A
        step carries the bars that closed at its `t`; a symbol with no bar then is absent from
        it. The simulator makes its touch from the close and `half_spread_bps`: 2.0 for a
        crypto-only tape, 1.0 when any equity is on it, unless given."""
        names = self._symbols(symbols)
        if not names:
            raise TapeError("a tape needs at least one symbol")
        seconds = self._timeframe(timeframe)
        _horizon(horizon)
        start_ts, end_ts = parse_time(start), parse_time(end)
        if end_ts <= start_ts:
            raise TapeError("a tape's end must come after its start")
        if half_spread_bps is None:
            spread = 2.0 if all(is_crypto(name) for name in names) else 1.0
        else:
            spread = _float(half_spread_bps)
            if spread is None or spread < 0:
                raise TapeError(f"half_spread_bps must be zero or more, got {half_spread_bps!r}")
        now = float(self.clock())
        by_time: dict[str, dict[str, dict[str, float]]] = {}
        for crypto in (True, False):
            group = [name for name in names if is_crypto(name) == crypto]
            if not group:
                continue
            for name, rows in self._closed_bars(group, timeframe, start_ts, end_ts, now).items():
                for bar in rows:
                    by_time.setdefault(bar["t"], {})[name] = {key: bar[key] for key in ("o", "h", "l", "c", "v")}
        steps = [
            {"t": t, "bars": {name: by_time[t][name] for name in names if name in by_time[t]}}
            for t in sorted(by_time)  # one fixed-width UTC format: text order is time order
        ]
        return {
            "venue": "alpaca",
            "horizon": horizon,
            "step_seconds": seconds,
            "half_spread_bps": float(spread),
            "symbols": names,
            "timeframe": timeframe,
            "steps": steps,
        }


# ---------------------------------------------------------------------- kalshi

def listed_close(row: "dict[str, Any]", close_ts: float) -> float:
    """The close an open listing showed for a market that has since settled.

    A settled row's `close_time` is when trading really stopped. A market that may close early
    (a game closes when a winner is declared) listed its latest expiration while it was open;
    showing the real moment would tell a strategy when every game ends. An early close is
    recognised by its time, as `ltcm.backtest.listed_close` does: a scheduled close falls on a
    whole minute, a declared result almost never does."""
    if not row.get("can_close_early") or int(close_ts) % 60 == 0:
        return close_ts
    for key in ("latest_expiration_time", "scheduled_close_time"):
        try:
            value = parse_time(row.get(key)) if row.get(key) else None
        except TapeError:
            value = None
        if value is not None and value > close_ts:
            return value
    return close_ts


def _day_windows(start_ts: float, end_ts: float) -> "list[tuple[int, int]]":
    """[start, end] cut on UTC midnights, so a whole day always asks History the same URL (its
    disk cache is keyed by URL). Kalshi's close-time bounds are both inclusive (Sept 19, 2026)."""
    out: list[tuple[int, int]] = []
    lo, last = int(math.floor(start_ts)), int(math.floor(end_ts))
    while lo <= last:
        hi = min(last, (lo // DAY + 1) * DAY - 1)
        out.append((lo, hi))
        lo = hi + 1
    return out


class KalshiData:
    """Kalshi markets for the live `ctx`, and settled ones resampled into a tape.

    `market_data` is a `ltcm.data.kalshi.KalshiMarketData` (or anything with its
    `markets(series_ticker=, status=, limit=, cursor=, ...)`); `history` is a
    `ltcm.history.History` (or anything with its `kalshi_settled` and `kalshi_candles_many`).
    Only `tape()` needs a history. `seed` orders the events a capped tape keeps.
    """

    def __init__(self, market_data: Any, history: Any = None, *, clock: Callable[[], float] = time.time, seed: Any = 7):
        self.market_data = market_data
        self.history = history
        self.clock = clock
        self.seed = seed

    @staticmethod
    def _series(series: Iterable[str]) -> "list[str]":
        if isinstance(series, str):
            series = [series]
        out: list[str] = []
        for raw in series or ():
            name = str(raw or "").strip().upper()
            if not _SERIES.match(name):
                raise TapeError(f"not a Kalshi series: {raw!r}")
            if name not in out:
                out.append(name)
        return out

    # ---------------------------------------------------------------- snapshot
    def markets(self, series: "list[str]", *, max_hours_to_close: float = 24.0, limit: int = 200) -> "list[dict[str, Any]]":
        """The open markets of these series closing within `max_hours_to_close`, soonest first,
        in the CONTRACT.md shape. Only a market with a two-sided touch is shown; at most `limit`
        rows (the soonest to close)."""
        names = self._series(series)
        hours = _float(max_hours_to_close)
        if hours is None or hours <= 0:
            raise TapeError(f"max_hours_to_close must be positive, got {max_hours_to_close!r}")
        now = float(self.clock())
        horizon_ts = now + hours * 3600.0
        rows: dict[str, tuple[float, dict[str, Any]]] = {}
        for name in names:
            cursor = None
            for _ in range(MAX_MARKET_PAGES):
                try:
                    page = self.market_data.markets(
                        series_ticker=name,
                        status="open",
                        limit=1000,
                        cursor=cursor,
                        min_close_ts=int(now),
                        max_close_ts=int(math.ceil(horizon_ts)),
                        mve_filter="exclude",
                    )
                except Exception as exc:
                    raise TapeError(f"kalshi markets {name}: {type(exc).__name__}: {exc}") from exc
                listed = page.get("markets") if isinstance(page, dict) else None
                if not isinstance(listed, list):
                    raise TapeError(f"kalshi markets {name}: no markets array")
                for raw in listed:
                    shown = self._live_row(raw, name, now, horizon_ts)
                    if shown is not None:
                        rows[shown[1]["market"]] = shown
                cursor = page.get("cursor")
                if not cursor or not listed:
                    break
        ordered = sorted(rows.values(), key=lambda pair: (pair[0], pair[1]["market"]))
        return [row for _, row in ordered[: max(0, int(limit))]]

    @staticmethod
    def _live_row(raw: Any, series: str, now: float, horizon_ts: float) -> "tuple[float, dict[str, Any]] | None":
        if not isinstance(raw, dict) or not raw.get("ticker"):
            return None
        if str(raw.get("status") or "active").lower() not in ("open", "active"):
            return None
        try:
            close_ts = parse_time(raw.get("close_time"))
        except TapeError:
            return None
        if not now < close_ts <= horizon_ts:
            return None
        bid, ask = _float(raw.get("yes_bid")), _float(raw.get("yes_ask"))
        if not two_sided(bid, ask):
            return None
        ticker = str(raw["ticker"]).upper()
        return close_ts, {
            "market": ticker,
            "series": series,
            "title": str(raw.get("title") or ""),
            "yes_bid": bid,
            "yes_ask": ask,
            "close_time": iso(close_ts),
            "hours_to_close": round((close_ts - now) / 3600.0, 4),
            "volume_24h": _float(raw.get("volume_24h")) or 0.0,
            "open_interest": _float(raw.get("open_interest")) or 0.0,
            "strike": parse_strike(ticker, raw),
        }

    # -------------------------------------------------------------------- tape
    def tape(
        self,
        series: "list[str]",
        *,
        start: str,
        end: str,
        step_seconds: int = 300,
        horizon: str = "hour",
        max_markets: int = 400,
    ) -> "dict[str, Any]":
        """A replay tape of the settled markets of these series that closed in [start, end].

        Steps fall on the `step_seconds` grid. At a step `t` a market's row carries the close of
        its last one-minute candle at or before `t`, and `yes_ask_low` / `yes_bid_high`, the
        lowest ask and highest bid of the candles inside `(t - step, t]` (the touch itself when
        there were none). A market is in a step only from its first candle until it closes, and
        only while its touch is two-sided, which is what `markets()` shows live. A market with
        no such step is skipped, as is one whose result is not yes or no.

        `max_markets` caps the markets kept. Events are read whole, in an order seeded from
        their tickers, until the cap is met, so the cap also bounds the candle requests and a
        kept event shows its whole two-sided ladder. `results` covers exactly the markets kept.
        """
        if self.history is None:
            raise TapeError("a Kalshi tape needs a History to read settled markets and candles")
        names = self._series(series)
        if not names:
            raise TapeError("a tape needs at least one series")
        _horizon(horizon)
        try:
            step = int(step_seconds)
        except (TypeError, ValueError) as exc:
            raise TapeError(f"step_seconds must be a whole number, got {step_seconds!r}") from exc
        if step < 60:
            raise TapeError("step_seconds must be at least 60: the candles are one minute wide")
        cap = max(0, int(max_markets))
        start_ts, end_ts = parse_time(start), parse_time(end)
        if end_ts <= start_ts:
            raise TapeError("a tape's end must come after its start")

        events, listed = self._settled_events(names, start_ts, end_ts)
        by_time: dict[int, list[dict[str, Any]]] = {}
        results: dict[str, str] = {}
        scanned = 0
        for event in sorted(events, key=lambda name: self._hash("event|" + name)):
            if len(results) >= cap:
                break
            members = sorted(events[event], key=lambda m: self._hash(m["ticker"]))
            scanned += len(members)
            lo = min(m["candles_from"] for m in members)
            hi = max(m["close_ts"] for m in members)
            try:
                candles = self.history.kalshi_candles_many(
                    [m["ticker"] for m in members], start_ts=lo, end_ts=hi, period_minutes=1
                )
            except Exception as exc:
                raise TapeError(f"kalshi candles {event}: {type(exc).__name__}: {exc}") from exc
            for market in members:
                if len(results) >= cap:
                    break
                rows = self._market_steps(market, (candles or {}).get(market["ticker"]) or [], start_ts, end_ts, step)
                if not rows:
                    continue
                results[market["ticker"]] = market["result"]
                for t, row in rows:
                    by_time.setdefault(t, []).append(row)
        steps = [
            {"t": iso(t), "markets": sorted(by_time[t], key=lambda row: (row["close_time"], row["market"]))}
            for t in sorted(by_time)
        ]
        return {
            "venue": "kalshi",
            "horizon": horizon,
            "step_seconds": step,
            "series": names,
            "steps": steps,
            "results": results,
            "meta": {"listed": listed, "scanned": scanned, "kept": len(results)},
        }

    def _hash(self, text: str) -> bytes:
        return hashlib.sha256(f"{self.seed}|{text}".encode("utf-8")).digest()

    def _settled_events(self, names: "list[str]", start_ts: float, end_ts: float) -> "tuple[dict[str, list[dict[str, Any]]], int]":
        """The settled yes/no markets closing in [start, end], grouped by event, and their count."""
        seen: set[str] = set()
        events: dict[str, list[dict[str, Any]]] = {}
        for name in names:
            for lo, hi in _day_windows(start_ts, end_ts):
                try:
                    rows = self.history.kalshi_settled(name, start_ts=lo, end_ts=hi)
                except Exception as exc:
                    raise TapeError(f"kalshi settled {name} {iso(lo)}..{iso(hi)}: {type(exc).__name__}: {exc}") from exc
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    ticker = str(row.get("ticker") or "").upper()
                    result = str(row.get("result") or "").lower()
                    if not ticker or ticker in seen or result not in ("yes", "no"):
                        continue
                    try:
                        close_ts = parse_time(row.get("close_time"))
                    except TapeError:
                        continue
                    if not start_ts <= close_ts <= end_ts:
                        continue
                    try:
                        open_ts = parse_time(row.get("open_time"))
                    except TapeError:
                        open_ts = start_ts - CANDLE_WARMUP_SECONDS
                    if open_ts >= close_ts:
                        continue
                    seen.add(ticker)
                    # Whole hours, so two tapes over nearby windows ask History the same URLs.
                    candles_from = int(max(open_ts, start_ts - CANDLE_WARMUP_SECONDS)) // 3600 * 3600
                    event = str(row.get("event_ticker") or "-".join(ticker.split("-")[:2]))
                    events.setdefault(event, []).append({
                        "ticker": ticker,
                        "series": name,
                        "title": str(row.get("title") or ""),
                        "result": result,
                        "close_ts": close_ts,
                        "close_time": iso(listed_close(row, close_ts)),
                        "listed_close_ts": listed_close(row, close_ts),
                        "candles_from": candles_from,
                        "strike": parse_strike(ticker, row),
                    })
        return events, len(seen)

    @staticmethod
    def _market_steps(
        market: "dict[str, Any]", candles: "list[dict[str, Any]]", start_ts: float, end_ts: float, step: int
    ) -> "list[tuple[int, dict[str, Any]]]":
        """One market's rows on the step grid: (step time, row), oldest first."""
        usable = sorted(
            (c for c in candles if isinstance(c, dict) and isinstance(c.get("ts"), (int, float)) and not isinstance(c.get("ts"), bool)),
            key=lambda c: c["ts"],
        )
        if not usable:
            return []
        ends = [int(c["ts"]) for c in usable]
        volume = [0.0]
        for candle in usable:
            volume.append(volume[-1] + max(0.0, _float(candle.get("volume")) or 0.0))
        close_ts = market["close_ts"]
        first = int(math.ceil(max(start_ts, ends[0]) / step)) * step
        out: list[tuple[int, dict[str, Any]]] = []
        for t in range(first, int(math.floor(end_ts)) + 1, step):
            if t >= close_ts:
                break  # trading has stopped: nothing to show, and the result is about to be known
            index = bisect.bisect_right(ends, t) - 1
            candle = usable[index]
            bid, ask = _float(candle.get("yes_bid_close")), _float(candle.get("yes_ask_close"))
            if not two_sided(bid, ask):
                continue
            inside = usable[bisect.bisect_right(ends, t - step) : index + 1]
            lows = [ask] + [v for v in (_float(c.get("yes_ask_low")) for c in inside) if v is not None and v > 0.0]
            highs = [bid] + [v for v in (_float(c.get("yes_bid_high")) for c in inside) if v is not None and v < 1.0]
            day = volume[index + 1] - volume[bisect.bisect_right(ends, t - DAY)]
            out.append((t, {
                "market": market["ticker"],
                "series": market["series"],
                "title": market["title"],
                "yes_bid": bid,
                "yes_ask": ask,
                "yes_ask_low": min(lows),
                "yes_bid_high": max(highs),
                "close_time": market["close_time"],
                "hours_to_close": round((market["listed_close_ts"] - t) / 3600.0, 4),
                "volume_24h": round(max(0.0, day), 2),
                "open_interest": _float(candle.get("open_interest")) or 0.0,
                "strike": market["strike"],
            }))
        return out


# ----------------------------------------------------------------- smoke check

def load_env(path: Any) -> "dict[str, str]":
    """`NAME=value` lines from a file (comments, blank lines and `export ` tolerated). The values
    are secrets: they are handed to whoever asked and never printed."""
    out: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[name.strip()] = value
    return out


def _smoke() -> int:
    """`python3 -m league.tapes`: one live read of each kind. Prints counts and samples only."""
    import json
    import tempfile
    from pathlib import Path

    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.data.kalshi import KalshiMarketData
    from ltcm.history import History

    root = Path(__file__).resolve().parent.parent
    token = load_env(root / ".env").get("GATEWAY_TOKEN", "")
    gateway_url = json.loads((root / "ltcm" / "config.json").read_text(encoding="utf-8")).get("gateway_url")
    now = time.time()
    failed = 0

    print("== alpaca (through the gateway) ==")
    if not token or not gateway_url:
        print("skipped: GATEWAY_TOKEN in .env and gateway_url in ltcm/config.json are both needed")
        failed += 1
    else:
        try:
            client = VenueClient(None, gateway_url=gateway_url, gateway=GatewaySigner(token), venue="alpaca-paper")
            data = AlpacaData(client)
            symbols = ["BTC/USD", "ETH/USD"]
            bars = data.bars(symbols, "5Min", start=iso(now - 6 * 3600), end=iso(now), limit=500)
            for symbol in symbols:
                rows = bars[symbol]
                print(f"{symbol}: {len(rows)} closed 5Min bars in the last 6 hours")
                if rows:
                    print(f"  first {rows[0]}")
                    print(f"  last  {rows[-1]}")
            print(f"quotes: {data.quotes(symbols + ['SPY'])}")
            tape = data.tape(symbols, "5Min", start=iso(now - DAY), end=iso(now))
            print(f"tape, last 24 hours: {len(tape['steps'])} steps, step_seconds={tape['step_seconds']}, "
                  f"half_spread_bps={tape['half_spread_bps']}")
            if tape["steps"]:
                print(f"  first step {tape['steps'][0]['t']}, last step {tape['steps'][-1]['t']}")
        except TapeError as exc:
            print(f"failed: {exc}")
            failed += 1

    print("== kalshi (public API) ==")
    with tempfile.TemporaryDirectory(prefix="league-tapes-") as cache_dir:
        try:
            kalshi = KalshiData(KalshiMarketData(), History(cache_dir=cache_dir, verbose=False))
            live = kalshi.markets(["KXBTCD"], max_hours_to_close=24)
            print(f"KXBTCD: {len(live)} live markets closing within 24 hours with a two-sided quote")
            if live:
                print(f"  first {live[0]}")
            began = time.monotonic()
            tape = kalshi.tape(["KXBTCD"], start=iso(now - 12 * 3600), end=iso(now), max_markets=400)
            took = time.monotonic() - began
            print(f"KXBTCD tape, last 12 hours: {len(tape['steps'])} steps, {len(tape['results'])} markets, "
                  f"{len(tape['results'])} results, meta={tape['meta']}, {took:.1f}s, "
                  f"{kalshi.history.requests} requests")
            if tape["steps"]:
                step = tape["steps"][-1]
                print(f"  last step {step['t']}: {len(step['markets'])} markets, first {step['markets'][0]}")
        except TapeError as exc:
            print(f"failed: {exc}")
            failed += 1
    return 1 if failed else 0


__all__ = [
    "TIMEFRAME_SECONDS",
    "TapeError",
    "AlpacaData",
    "KalshiData",
    "is_crypto",
    "parse_time",
    "iso",
    "parse_strike",
    "two_sided",
    "listed_close",
    "load_env",
]


if __name__ == "__main__":
    raise SystemExit(_smoke())

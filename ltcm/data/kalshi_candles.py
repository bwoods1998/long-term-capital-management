"""Kalshi's own hourly record of each market: volume, open interest and prices by the hour (Sept 25,
2026, the Kalshi-scale run's `kalshi_candles` recorder, league/open_feeds.py).

Workstream K2 measures capacity -- how much a family could earn at 1x-8x its size -- and its own fills
say only what it bought. What traded in the market around it is Kalshi's public record: every
market's hourly candle (contracts traded, open interest, the traded price range and the yes bid and
ask at the hour's open and close). A candle is final once its hour has ended, and Kalshi stamps it
with that end (`end_period_ts`), so the history can be backfilled honestly.

The trade tape itself (`/markets/trades`) was measured on Sept 25, 2026 at 06:26Z: 6,000 prints in
one minute across all markets, and one MLB game market printed 1,000 in six minutes; per-market
prints cannot be paged within the feeds lane's budget. The candles say the same per hour in one
request for up to a hundred markets.

    GET https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXHIGHNY&min_close_ts=..&max_close_ts=..&limit=1000
      markets[]: ticker, event_ticker, status, open_time, close_time, volume_fp, result, ... ; cursor
    GET https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=A,B&start_ts=..&end_ts=..&period_interval=60
      markets[]: market_ticker, candlesticks[]: end_period_ts, volume_fp, open_interest_fp,
      price {open,high,low,close,mean,previous}_dollars (traded; null in an hour with no trade),
      yes_bid / yes_ask {open,high,low,close}_dollars. At most 100 markets a request ("requested 101
      markets, max markets: 100", probed Sept 25, 2026); a market with no activity in an hour has no
      candle for it.

Public market data; the host is already on the House's allowlist (api.elections.kalshi.com).
"""

from __future__ import annotations

import math
import time
import urllib.parse
from datetime import datetime
from typing import Any, Mapping, Sequence

from . import CONTACT_USER_AGENT, HttpTransport, read_json, require

HOST = "https://api.elections.kalshi.com/trade-api/v2"
MARKETS_URL = HOST + "/markets"
CANDLES_URL = HOST + "/markets/candlesticks"
#: Kalshi's batch candlestick endpoint answers at most this many markets a request.
MAX_BATCH = 100
MIN_INTERVAL = 0.2


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _epoch(text: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def parse_markets(payload: Any) -> tuple[list[dict[str, Any]], str]:
    """A markets page as ([{ticker, event, status, open, close, volume, result}], cursor)."""
    rows = payload.get("markets") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), "kalshi markets: no markets")
    out = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("ticker"):
            continue
        out.append({"ticker": str(row["ticker"]), "event": row.get("event_ticker"), "status": row.get("status"),
                    "open": _epoch(row.get("open_time")), "close": _epoch(row.get("close_time")),
                    "volume": _number(row.get("volume_fp")) or 0.0, "result": row.get("result") or None})
    return out, str(payload.get("cursor") or "")


def _price(block: Any, name: str) -> float | None:
    return _number(block.get(f"{name}_dollars")) if isinstance(block, Mapping) else None


def candle_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One hourly candle, prices in dollars (the YES side), or None when it has no end."""
    end = _number(raw.get("end_period_ts"))
    if end is None:
        return None
    price, bid, ask = raw.get("price") or {}, raw.get("yes_bid") or {}, raw.get("yes_ask") or {}
    return {"end": end, "volume": _number(raw.get("volume_fp")) or 0.0, "open_interest": _number(raw.get("open_interest_fp")),
            "open": _price(price, "open"), "high": _price(price, "high"), "low": _price(price, "low"),
            "close": _price(price, "close"), "mean": _price(price, "mean"),
            "bid_close": _price(bid, "close"), "ask_close": _price(ask, "close"),
            "bid_high": _price(bid, "high"), "ask_low": _price(ask, "low")}


def parse_candles(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """The batch answer as {ticker: [candle, ...]} oldest first."""
    rows = payload.get("markets") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), "kalshi candlesticks: no markets")
    out: dict[str, list[dict[str, Any]]] = {}
    for market in rows:
        if not isinstance(market, Mapping) or not market.get("market_ticker"):
            continue
        candles = [c for c in (candle_row(x) for x in market.get("candlesticks") or [] if isinstance(x, Mapping)) if c is not None]
        out[str(market["market_ticker"])] = sorted(candles, key=lambda c: c["end"])
    return out


class KalshiCandles:
    """A series' markets and their hourly candles, from Kalshi's public market data."""

    def __init__(self, transport: Any = None, *, timeout: float = 20.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _json(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                         timeout=self.timeout, what=what)

    def markets(self, series: str, *, closing_from: float, closing_to: float, pages: int = 3) -> list[dict[str, Any]]:
        """The series' markets closing in [closing_from, closing_to], at most `pages` pages of 1000."""
        out: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(max(1, int(pages))):
            params = {"series_ticker": series, "min_close_ts": int(closing_from), "max_close_ts": int(math.ceil(closing_to)),
                      "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            rows, cursor = parse_markets(self._json(f"{MARKETS_URL}?{urllib.parse.urlencode(params)}", f"kalshi markets {series}"))
            out.extend(rows)
            if not cursor:
                break
        return out

    def candles(self, tickers: Sequence[str], start: float, end: float) -> dict[str, list[dict[str, Any]]]:
        """Hourly candles of up to `MAX_BATCH` markets whose hours end in [start, end]."""
        require(0 < len(tickers) <= MAX_BATCH, f"kalshi candlesticks: 1 to {MAX_BATCH} markets a request")
        params = {"market_tickers": ",".join(tickers), "start_ts": int(start), "end_ts": int(end), "period_interval": 60}
        return parse_candles(self._json(f"{CANDLES_URL}?{urllib.parse.urlencode(params, safe=',')}", "kalshi candlesticks"))


__all__ = ["CANDLES_URL", "HOST", "KalshiCandles", "MARKETS_URL", "MAX_BATCH", "candle_row", "parse_candles", "parse_markets"]

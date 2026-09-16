"""Backtest: replay a strategy's `decide(kit, params)` against venue history.

A strategy (`ltcm/strategies.py`) is judged on the floor by its record, which takes days of
settlements to mean anything. This engine gives the same code a record in minutes: it steps a
simulated clock from `start` to `end`, hands the strategy a `BacktestKit` that answers every
`Kit` call from history *as of that moment* (`ltcm/history.py`), and books what the strategy
proposes in a simulator whose fills are deliberately conservative.

    python3 -m ltcm.backtest --spec spec.json      # or the spec as JSON on stdin
    -> one stdout line: BACKTEST-RESULT {...report...}

What the kit sees at simulated time t:

* Kalshi markets with `open_time <= t < close_time`, priced from the last candlestick whose
  period ended at or before t (no candle yet: no prices). `volume_24h` sums candle volumes in
  (t - 24h, t]. Nothing a settled row knows about its future (result, final volume) is shown.
* Coinbase bars that had closed by t (`start + granularity <= t`); a quote is the last closed
  five-minute close -/+ a half-spread (1 bp by default).
* `weather` / `weather_cities` stop the run as unsupported: there is no NWS forecast history.

The simulator (fill_model "conservative"):

* Kalshi buy of leg L at p, not post-only: fills at once at the leg's ask if p >= ask (YES ask
  = yes_ask, NO ask = 1 - yes_bid), paying the taker fee ceil(0.07 p (1 - p) x 100) / 100 per
  contract; else it rests. Post-only orders that would cross are rejected, as the venue does.
  A resting bid fills at its limit, fee 0, only on a candle that ended after it was placed and
  shows the other side trading strictly through it (YES bid p: yes_ask_low < p; NO bid q:
  yes_bid_high > 1 - q). A candle that began before the order existed is judged on its close,
  not its extremes, so an hourly low printed before the order cannot fill it; and once an order
  rests on a market still priced by the hour, that market's minute candles from the order's
  hour on are fetched before the next step and replace the hourly ones. Sells mirror this.
  Resting orders expire at the market's close; positions settle at close on the result.
* Coinbase: marketable non-post-only limits take at the quote with the taker fee (0.60%);
  otherwise the order rests and fills at its limit on a later five-minute candle whose low
  (buy) / high (sell) reaches it, with the maker fee (0.25%). Spot is long only.
* The floor's exit plans are honoured at step resolution: a stop or target on the exit-side
  mark, and for crypto the holding-period time stop, close the position at the bid as a taker.
* Each intent's notional is capped at 10x `learning_usd`; at most 5 intents and 20 cancels a
  run, as on the floor; a strategy may cancel only its own orders.

fill_model "touch" is the optimistic bracket for makers: a resting Kalshi order also fills when
the other side touches its price, or a trade prints at or through it, on a later candle.

Standard library only; importable in a desk's sandbox (`FLOOR_EXTRAS`).
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import copy
import json
import math
import os
import random
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

STARTERS_DIR = Path(__file__).resolve().parent / "starters"
RESULT_PREFIX = "BACKTEST-RESULT "

#: Mirrors of the floor's per-run limits (`ltcm/strategies.py` DEFAULTS and RUNNER).
MAX_INTENTS_PER_RUN = 5
MAX_CANCELS_PER_RUN = 20
NOTIONAL_CAP_MULTIPLE = 10
BOOTSTRAP_RESAMPLES = 2000
EPS = 1e-9

DEFAULT_SPEC: dict[str, Any] = {
    "strategy": None,
    "code": None,
    "params": {},
    "start": None,
    "end": None,
    "step_minutes": 15,
    "series": None,
    "products": None,
    "learning_usd": 10,
    "fill_model": "conservative",
    "max_markets": 3000,
    "seed": 7,
    # Engine knobs beyond the contract, each with the default the contract implies.
    "min_volume": None,           # settled-market volume floor; None: 500 for the board, 0 for series
    "max_pages": None,            # settled listing pages per window: None is 20 a series-day, 50 a board six hours
    "half_spread_bps": 1.0,       # Coinbase quote = close -/+ this
    "coinbase_maker_fee": 0.0025,
    "coinbase_taker_fee": 0.006,
    "max_seconds": 0,             # wall-clock budget; 0 is none. A stopped run reports what it had.
    "verbose": True,              # progress lines on stderr
}

#: Kit interval -> Coinbase granularity (as `ltcm/data/coinbase.py` spells them).
INTERVALS = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "60m": "ONE_HOUR",
    "2h": "TWO_HOUR",
    "6h": "SIX_HOUR",
    "1d": "ONE_DAY",
}
GRANULARITY_SECONDS = {
    "ONE_MINUTE": 60,
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "TWO_HOUR": 7200,
    "SIX_HOUR": 21600,
    "ONE_DAY": 86400,
}
QUOTE_GRANULARITY = "FIVE_MINUTE"
#: `kit.products()` with no `products` in the spec: the most traded Coinbase USD spot pairs
#: (Sept 2026). The venue's ranking at a past moment is not public; this list stands in for it.
DEFAULT_PRODUCTS = (
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "LINK-USD", "AVAX-USD",
    "LTC-USD", "BCH-USD", "SUI-USD", "HBAR-USD", "XLM-USD", "DOT-USD", "SHIB-USD", "HYPE-USD",
    "PEPE-USD", "UNI-USD", "AAVE-USD", "NEAR-USD",
)
#: A market living longer than this gets hourly candles, plus minute candles near its close.
LONG_LIFE_SECONDS = 3 * 3600
FINE_WINDOW_SECONDS = 90 * 60
VOLUME_LOOKBACK_SECONDS = 24 * 3600
#: Candle requests are grouped so a batch asks at most this many market-periods.
BATCH_BUDGET = 9000
SERIES_LITERAL = re.compile(r"""["'](KX[A-Z0-9]{2,})["']""")


#: "conservative": a resting order fills only when the book trades strictly through it (its fills
#: are the adverse ones, so a maker's P&L reads low). "touch": it also fills when the other side
#: touches its price or a trade prints at or through it (queue position ignored; reads high).
#: The two bracket a maker strategy; takers fill the same way under both.
FILL_MODELS = ("conservative", "touch")


class Unsupported(RuntimeError):
    """Raised by a kit call history cannot answer (weather forecasts)."""


def product_id(symbol: Any) -> str | None:
    """`BTC-USD` from `BTC-USD`, `BTC/USD` or `BTCUSD`; None for anything else."""
    raw = str(symbol or "").strip().upper().replace("/", "-").replace("_", "-")
    if "-" not in raw and raw.endswith("USD") and len(raw) > 3:
        raw = raw[:-3] + "-USD"
    parts = raw.split("-")
    if len(parts) != 2 or not all(part and part.isalnum() for part in parts):
        return None
    return raw


# ----------------------------------------------------------------------------- time


def parse_time(value: Any) -> float:
    """An ISO-8601 UTC stamp (or epoch seconds) as epoch seconds."""
    if isinstance(value, bool):
        raise ValueError("a bool is not a time")
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty time")
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    moment = datetime.fromisoformat(raw)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d")


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _text_number(value: float) -> str:
    """A float as a plain decimal string (no exponent), the way the floor's data layer prints."""
    try:
        return format(Decimal(f"{float(value):.12g}").normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(value)


def _dollars(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(f"{value:.4f}")


def _clean(text: Any, limit: int = 300) -> str:
    """A note safe for the public tape: no angle brackets, bounded."""
    return str(text).replace("<", "(").replace(">", ")")[:limit]


def kalshi_taker_fee(price: float) -> float:
    """Kalshi's taker fee per contract: ceil(0.07 x p x (1 - p) x 100) / 100 dollars."""
    return math.ceil(round(0.07 * price * (1.0 - price) * 100.0, 9)) / 100.0


# -------------------------------------------------------------------------- markets


def listed_close(row: Mapping[str, Any], close_ts: float) -> float:
    """The close time an open listing showed for a market that has since settled.

    A settled row's `close_time` is when trading actually stopped. A market that may close early
    (a game market closes when a winner is declared) listed its latest expiration as its close
    while it was open -- a baseball game on Sept 16, 2026 showed a close six days out -- and only
    the settled row shows the moment the outcome was known. Showing that moment to a strategy
    would tell it when every game ends. An early close is recognised by its time (a scheduled
    close falls on a whole minute; a declared result almost never does); the listing then showed
    `latest_expiration_time`. Trading and settlement still stop at the real close."""
    if not row.get("can_close_early") or int(close_ts) % 60 == 0:
        return close_ts
    for key in ("latest_expiration_time", "scheduled_close_time"):
        try:
            value = parse_time(row.get(key)) if row.get(key) else None
        except ValueError:
            value = None
        if value is not None and value > close_ts:
            return value
    return close_ts



class Market:
    """One settled Kalshi market, replayable at any moment of its life."""

    __slots__ = (
        "ticker", "series", "event", "open_ts", "close_ts", "listed_close_ts", "payout_yes", "static", "volume",
        "ends", "periods", "candles", "_volume_prefix", "_last", "_decimals", "fine_from",
    )

    def __init__(self, row: Mapping[str, Any]):
        self.ticker = str(row.get("ticker") or "").upper()
        self.event = str(row.get("event_ticker") or "-".join(self.ticker.split("-")[:2]))
        self.series = self.ticker.split("-")[0]
        self.open_ts = parse_time(row.get("open_time"))
        self.close_ts = parse_time(row.get("close_time"))
        self.listed_close_ts = listed_close(row, self.close_ts)
        self.volume = _num(row.get("volume"), 0.0) or 0.0
        result = str(row.get("result") or "").lower()
        if result == "yes":
            self.payout_yes: float | None = 1.0
        elif result == "no":
            self.payout_yes = 0.0
        else:
            self.payout_yes = _num(row.get("settlement_value"))
        # What an open market's row showed; nothing here is known only after the close.
        self.static = {
            "ticker": self.ticker,
            "event_ticker": row.get("event_ticker"),
            "title": row.get("title"),
            "yes_sub_title": row.get("yes_sub_title"),
            "no_sub_title": row.get("no_sub_title"),
            "status": "active",
            "result": None,
            "open_time": iso(self.open_ts),
            "close_time": iso(self.listed_close_ts),
            "expiration_time": row.get("expiration_time"),
            "can_close_early": bool(row.get("can_close_early")),
            "price_ranges": row.get("price_ranges") or [],
            "strike_type": row.get("strike_type"),
            "floor_strike": row.get("floor_strike"),
            "cap_strike": row.get("cap_strike"),
        }
        self.ends: list[int] = []
        self.periods: list[int] = []
        self.candles: list[dict[str, Any]] = []
        self._volume_prefix: list[float] = [0.0]
        self._last: list[float | None] = []
        self._decimals: dict[int, tuple] = {}
        self.fine_from = self.open_ts

    def attach(self, candles: Iterable[tuple[int, Mapping[str, Any]]]) -> None:
        """Candles as (period seconds, candle), non-overlapping, any order."""
        rows = sorted(((int(c["ts"]), period, dict(c)) for period, c in candles), key=lambda r: (r[0], -r[1]))
        self.ends, self.periods, self.candles = [], [], []
        for end, period, candle in rows:
            if self.ends and self.ends[-1] == end:
                continue  # the finer duplicate of the same instant is dropped; the coarse one kept
            self.ends.append(end)
            self.periods.append(period)
            self.candles.append(candle)
        prefix = [0.0]
        last: list[float | None] = []
        for candle in self.candles:
            prefix.append(prefix[-1] + (_num(candle.get("volume"), 0.0) or 0.0))
            traded = candle.get("price_close")
            last.append(traded if traded is not None else (last[-1] if last else None))
        self._volume_prefix = prefix
        self._last = last
        self._decimals = {}

    def refine(self, new_from: float, minute_candles: Iterable[Mapping[str, Any]]) -> bool:
        """Replace the hourly candles after `new_from` (an hour boundary) with minute candles,
        so fills on an order resting there are judged minute by minute."""
        if new_from >= self.fine_from:
            return False
        minutes = [(60, dict(c)) for c in minute_candles if new_from < int(c["ts"]) <= self.fine_from]
        if not minutes:
            return False  # no minute history came back: the hourly evidence stays
        kept = [(period, candle) for end, period, candle in zip(self.ends, self.periods, self.candles) if period != 3600 or end <= new_from]
        self.fine_from = new_from
        self.attach(kept + minutes)
        return True

    def index_at(self, t: float) -> int:
        """Index of the last candle whose period ended at or before t, or -1."""
        return bisect.bisect_right(self.ends, t) - 1

    def is_open(self, t: float) -> bool:
        return self.open_ts <= t < self.close_ts

    def book(self, t: float) -> tuple[float | None, float | None]:
        """(yes_bid, yes_ask) at t, or (None, None) before the first candle."""
        index = self.index_at(t)
        if index < 0:
            return None, None
        candle = self.candles[index]
        return candle.get("yes_bid_close"), candle.get("yes_ask_close")

    def view(self, t: float) -> dict[str, Any]:
        """The market's row as an open-market listing showed it at t."""
        index = self.index_at(t)
        row = dict(self.static)
        if index < 0:
            row.update(yes_bid=None, yes_ask=None, no_bid=None, no_ask=None, last_price=None,
                       volume=Decimal(0), volume_24h=Decimal(0), open_interest=None)
            return row
        cached = self._decimals.get(index)
        if cached is None:
            candle = self.candles[index]
            bid, ask = candle.get("yes_bid_close"), candle.get("yes_ask_close")
            last = self._last[index]  # the last traded price, carried forward
            cached = (
                _dollars(bid),
                _dollars(ask),
                _dollars(None if ask is None else 1.0 - ask),
                _dollars(None if bid is None else 1.0 - bid),
                _dollars(last),
                None if candle.get("open_interest") is None else Decimal(_text_number(candle["open_interest"])),
            )
            self._decimals[index] = cached
        yes_bid, yes_ask, no_bid, no_ask, last, interest = cached
        low = bisect.bisect_right(self.ends, t - VOLUME_LOOKBACK_SECONDS)
        day_volume = self._volume_prefix[index + 1] - self._volume_prefix[low]
        row.update(
            yes_bid=yes_bid, yes_ask=yes_ask, no_bid=no_bid, no_ask=no_ask, last_price=last,
            volume=Decimal(_text_number(round(self._volume_prefix[index + 1], 2))),
            volume_24h=Decimal(_text_number(round(max(0.0, day_volume), 2))),
            open_interest=interest,
        )
        return row


class CryptoSeries:
    """Coinbase candles of one product at one granularity, loaded on demand."""

    __slots__ = ("product", "granularity", "seconds", "starts", "candles", "loaded_from", "failed")

    def __init__(self, product: str, granularity: str):
        self.product = product
        self.granularity = granularity
        self.seconds = GRANULARITY_SECONDS[granularity]
        self.starts: list[int] = []
        self.candles: list[dict[str, Any]] = []
        self.loaded_from: float | None = None
        self.failed = False

    def merge(self, rows: Iterable[Mapping[str, Any]]) -> None:
        found = {int(c["ts"]): dict(c) for c in self.candles}
        for row in rows:
            found[int(row["ts"])] = dict(row)
        self.starts = sorted(found)
        self.candles = [found[k] for k in self.starts]

    def closed_index(self, t: float) -> int:
        """Index of the last candle that had closed by t (start + granularity <= t), or -1."""
        return bisect.bisect_right(self.starts, t - self.seconds) - 1


class DataSet:
    """Everything the kit and the simulator read, loaded once (Kalshi) or on demand (Coinbase)."""

    def __init__(self, history: Any, start_ts: float, end_ts: float, *, say: Callable[[str], None], notes: list[str]):
        self.history = history
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.say = say
        self.notes = notes
        self.markets: dict[str, Market] = {}
        self.by_series: dict[str, list[Market]] = {}
        self.series_closes: dict[str, list[float]] = {}
        self.series_life: dict[str, float] = {}
        self.ordered: list[Market] = []
        self.closes: list[float] = []
        self.max_life = 0.0
        self.board = False
        self.loaded_series: set[str] = set()
        self.crypto: dict[tuple[str, str], CryptoSeries] = {}
        self.errors = 0
        self._noted: set[str] = set()
        #: Markets whose hourly candles are replaced by minute candles once an order rests on
        #: them (ticker -> the hour to refine from), fetched in batches before the next step.
        self.pending_refine: dict[str, float] = {}
        self.refined: set[str] = set()
        self.refine_tried: dict[str, float] = {}
        self.max_refine = 400

    def note_once(self, key: str, text: str) -> None:
        if key not in self._noted:
            self._noted.add(key)
            self.notes.append(_clean(text))

    # ------------------------------------------------------------------ kalshi
    def load_kalshi(self, *, series: list[str] | None, board: bool, max_markets: int, min_volume: float | None, max_pages: int) -> None:
        rows: list[dict[str, Any]] = []
        truncated_before = int(getattr(self.history, "truncated_listings", 0) or 0)
        if board:
            self.board = True
            floor = 500.0 if min_volume is None else float(min_volume)
            # The whole board closes more than 20,000 markets on a busy day (Sept 2026), so it is
            # listed six hours at a time.
            for lo, hi in self._days(hours=6):
                try:
                    rows.extend(self.history.kalshi_settled(None, start_ts=lo, end_ts=hi, max_pages=max_pages, min_volume=floor))
                except Exception as exc:
                    self.errors += 1
                    self.notes.append(_clean(f"settled board {iso(lo)}..{iso(hi)} failed: {type(exc).__name__}: {exc}"))
            chosen = self._dedupe(rows)
            chosen.sort(key=lambda r: -(_num(r.get("volume"), 0.0) or 0.0))
            if len(chosen) > max_markets:
                self.notes.append(f"board capped at {max_markets} of {len(chosen)} settled markets (highest volume first)")
            chosen = chosen[:max_markets]
        else:
            floor = 0.0 if min_volume is None else float(min_volume)
            for name in series or []:
                ok = False
                for lo, hi in self._days():
                    try:
                        rows.extend(self.history.kalshi_settled(name, start_ts=lo, end_ts=hi, max_pages=max_pages, min_volume=floor))
                        ok = True
                    except Exception as exc:
                        self.errors += 1
                        self.notes.append(_clean(f"settled series {name} {iso(lo)}..{iso(hi)} failed: {type(exc).__name__}: {exc}"))
                if ok:
                    self.loaded_series.add(str(name).upper())
            chosen = self._dedupe(rows)
            if len(chosen) > max_markets:
                # Every settlement keeps its most traded strikes: round-robin by rank within
                # the event, so a quiet night is not dropped wholesale for a busy afternoon.
                by_event: dict[str, list[dict[str, Any]]] = {}
                for row in chosen:
                    by_event.setdefault(str(row.get("event_ticker") or ""), []).append(row)
                ranked = []
                for members in by_event.values():
                    members.sort(key=lambda r: -(_num(r.get("volume"), 0.0) or 0.0))
                    ranked.extend((rank, -(_num(r.get("volume"), 0.0) or 0.0), r["ticker"], r) for rank, r in enumerate(members))
                ranked.sort(key=lambda x: (x[0], x[1], x[2]))
                self.notes.append(f"series capped at {max_markets} of {len(chosen)} settled markets (the most traded strikes of every event)")
                chosen = [x[3] for x in ranked[:max_markets]]
        truncated = int(getattr(self.history, "truncated_listings", 0) or 0) - truncated_before
        if truncated:
            self.notes.append(f"{truncated} settled listing(s) stopped at max_pages ({max_pages}) with more markets left; raise max_pages for the whole window")
        for row in chosen:
            try:
                market = Market(row)
            except (ValueError, TypeError):
                continue
            if market.close_ts <= market.open_ts:
                continue
            self.markets[market.ticker] = market
        self.ordered = sorted(self.markets.values(), key=lambda m: (m.close_ts, m.ticker))
        self.closes = [m.close_ts for m in self.ordered]
        self.max_life = max((m.close_ts - m.open_ts for m in self.ordered), default=0.0)
        for market in self.ordered:
            self.by_series.setdefault(market.series, []).append(market)
            self.series_life[market.series] = max(self.series_life.get(market.series, 0.0), market.close_ts - market.open_ts)
        for name, members in self.by_series.items():
            self.series_closes[name] = [m.close_ts for m in members]
        self.say(f"{len(self.markets)} settled markets loaded ({'board' if board else ', '.join(series or [])})")
        self._load_candles()

    def _days(self, hours: int = 24) -> list[tuple[int, int]]:
        """The window as listing windows of `hours` on a fixed UTC grid (so they cache)."""
        out = []
        size = int(hours) * 3600
        lo = int(self.start_ts)
        while lo <= self.end_ts:
            hi = min(int(self.end_ts), (lo // size + 1) * size - 1)
            out.append((lo, hi))
            lo = hi + 1
        return out

    @staticmethod
    def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            if ticker and row.get("open_time") and row.get("close_time"):
                seen[ticker] = row
        return list(seen.values())

    def _windows(self, market: Market) -> list[tuple[int, float, float]]:
        """(period minutes, from, to) windows for one market: hourly over a long life, minutes
        over the last ninety minutes (or the whole of a short life). They never overlap."""
        lo = max(market.open_ts, self.start_ts - VOLUME_LOOKBACK_SECONDS)
        if market.close_ts <= lo:
            return []
        if market.close_ts - market.open_ts <= LONG_LIFE_SECONDS:
            market.fine_from = math.floor(lo / 60.0) * 60
            return [(1, market.fine_from, market.close_ts)]
        fine_from = math.floor((market.close_ts - FINE_WINDOW_SECONDS) / 3600.0) * 3600
        fine_from = max(fine_from, math.floor(lo / 60.0) * 60)
        market.fine_from = fine_from
        windows = []
        if fine_from > lo:
            windows.append((60, lo, fine_from))
        windows.append((1, fine_from, market.close_ts))
        return windows

    def _load_candles(self) -> None:
        jobs: dict[int, list[tuple[float, float, Market]]] = {1: [], 60: []}
        for market in self.ordered:
            for period, lo, hi in self._windows(market):
                jobs[period].append((lo, hi, market))
        collected: dict[str, list[tuple[int, dict[str, Any]]]] = {m.ticker: [] for m in self.ordered}
        many = getattr(self.history, "kalshi_candles_many", None)
        total_jobs = sum(len(v) for v in jobs.values())
        done = 0
        last_said = time.monotonic()
        for period, items in jobs.items():
            if not items:
                continue
            groups = self._group(items, period) if callable(many) else [[item] for item in items]
            for group in groups:
                lo = min(item[0] for item in group)
                hi = max(item[1] for item in group)
                try:
                    if callable(many):
                        found = many([item[2].ticker for item in group], start_ts=int(lo), end_ts=int(math.ceil(hi)), period_minutes=period)
                    else:
                        market = group[0][2]
                        found = {market.ticker: self.history.kalshi_candles(market.series, market.ticker, start_ts=int(lo), end_ts=int(math.ceil(hi)), period_minutes=period)}
                except Exception as exc:
                    self.errors += 1
                    self.note_once(f"candles-{type(exc).__name__}", f"candle load failed ({type(exc).__name__}: {str(exc)[:160]}); those markets have no prices")
                    found = {}
                for item_lo, item_hi, market in group:
                    for candle in found.get(market.ticker) or []:
                        try:
                            ts = int(candle["ts"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        # Keep each window's own candles, so hourly and minute never overlap:
                        # hourly candles end by the minute window's start, minute ones after it.
                        if ts > item_hi or (period == 1 and ts <= item_lo):
                            continue
                        collected[market.ticker].append((period * 60, candle))
                done += len(group)
                if time.monotonic() - last_said > 15:
                    last_said = time.monotonic()
                    self.say(f"candles: {done}/{total_jobs} market windows")
        for market in self.ordered:
            market.attach(collected.get(market.ticker) or [])
        priced = sum(1 for m in self.ordered if m.candles)
        self.say(f"candles loaded: {priced}/{len(self.ordered)} markets have prices")

    @staticmethod
    def _group(items: list[tuple[float, float, Market]], period: int) -> list[list[tuple[float, float, Market]]]:
        """Batch requests: markets whose windows sit close together share one call, within
        the batch endpoint's limits (100 markets, market x periods under the budget)."""
        items = sorted(items, key=lambda x: (x[1], x[0]))
        groups: list[list[tuple[float, float, Market]]] = []
        current: list[tuple[float, float, Market]] = []
        lo = hi = 0.0
        seconds = period * 60
        for item in items:
            if current:
                new_lo, new_hi = min(lo, item[0]), max(hi, item[1])
                periods = int(math.ceil((new_hi - new_lo) / seconds)) + 1
                if len(current) + 1 <= 100 and periods * (len(current) + 1) <= BATCH_BUDGET:
                    current.append(item)
                    lo, hi = new_lo, new_hi
                    continue
                groups.append(current)
            current = [item]
            lo, hi = item[0], item[1]
        if current:
            groups.append(current)
        return groups

    def request_refine(self, market: Market, t: float) -> None:
        """Ask for minute candles from the hour of `t` to the minute window, when an order rests
        on a market still priced by the hour: an hourly candle cannot say whether the book
        traded through the order after it was placed or before."""
        hour = math.floor(t / 3600.0) * 3600
        if market.fine_from <= hour or self.refine_tried.get(market.ticker, math.inf) <= hour:
            return  # already minute-resolved there, or asked before and nothing finer came back
        known = market.ticker in self.refine_tried or market.ticker in self.pending_refine
        if not known and len(self.refine_tried) + len(self.pending_refine) >= self.max_refine:
            self.note_once("refine-cap", f"minute candles fetched for {self.max_refine} markets at most; later resting orders are judged on hourly candles")
            return
        self.pending_refine[market.ticker] = min(self.pending_refine.get(market.ticker, hour), hour)

    def flush_refine(self) -> None:
        if not self.pending_refine:
            return
        items = []
        for ticker, hour in sorted(self.pending_refine.items()):
            market = self.markets.get(ticker)
            if market is not None and hour < market.fine_from:
                items.append((hour, market.fine_from, market))
                self.refine_tried[ticker] = min(hour, self.refine_tried.get(ticker, hour))
        self.pending_refine.clear()
        many = getattr(self.history, "kalshi_candles_many", None)
        groups = self._group(items, 1) if callable(many) else [[item] for item in items]
        for group in groups:
            lo = min(item[0] for item in group)
            hi = max(item[1] for item in group)
            try:
                if callable(many):
                    found = many([item[2].ticker for item in group], start_ts=int(lo), end_ts=int(math.ceil(hi)), period_minutes=1)
                else:
                    market = group[0][2]
                    found = {market.ticker: self.history.kalshi_candles(market.series, market.ticker, start_ts=int(lo), end_ts=int(math.ceil(hi)), period_minutes=1)}
            except Exception as exc:
                self.errors += 1
                self.note_once(f"refine-{type(exc).__name__}", f"minute candles for resting orders failed ({type(exc).__name__}: {str(exc)[:160]}); hourly candles judged them")
                continue
            for item_lo, _item_hi, market in group:
                if market.refine(item_lo, found.get(market.ticker) or []):
                    self.refined.add(market.ticker)

    def open_markets(self, t: float, *, series: str | None = None, max_close: float | None = None) -> list[Market]:
        """Markets open at t, optionally of one series and closing by `max_close`."""
        if series is not None:
            members = self.by_series.get(series) or []
            closes = self.series_closes.get(series) or []
            life = self.series_life.get(series, 0.0)
        else:
            members, closes, life = self.ordered, self.closes, self.max_life
        out = []
        index = bisect.bisect_right(closes, t)
        stop = t + life
        if max_close is not None:
            stop = min(stop, max_close)
        while index < len(members):
            market = members[index]
            if market.close_ts > stop:
                break
            if market.open_ts <= t and (max_close is None or market.listed_close_ts <= max_close):
                out.append(market)
            index += 1
        return out

    # ---------------------------------------------------------------- coinbase
    def crypto_series(self, product: str, granularity: str, need_from: float) -> CryptoSeries | None:
        key = (product, granularity)
        series = self.crypto.get(key)
        if series is None:
            series = self.crypto[key] = CryptoSeries(product, granularity)
        if series.failed:
            return None
        seconds = series.seconds
        need_from = math.floor(need_from / seconds) * seconds
        if series.loaded_from is None or need_from < series.loaded_from:
            hi = self.end_ts if series.loaded_from is None else series.loaded_from - 1
            # The first read also takes a generous lookback, so a later, longer ask rarely reloads.
            lo = min(need_from, self.start_ts - 300 * seconds) if series.loaded_from is None else need_from
            try:
                rows = self.history.coinbase_candles(product, start_ts=int(lo), end_ts=int(hi), granularity=granularity)
            except Exception as exc:
                self.errors += 1
                series.failed = True
                self.note_once(f"coinbase-{product}-{granularity}", f"coinbase {product} {granularity} failed: {type(exc).__name__}: {str(exc)[:160]}")
                return None
            series.merge(rows)
            series.loaded_from = lo
        return series


# ------------------------------------------------------------------------------ kit


class BacktestKit:
    """The strategy's `kit`, answering from history as of the simulated time."""

    def __init__(self, data: DataSet, sim: "Simulator", t: float, *, products: list[str] | None, half_spread: float):
        self._data = data
        self._sim = sim
        self._t = t
        self._products = products
        self._half_spread = half_spread
        self.context = sim.context(t)
        self.log: list[str] = []
        self.unsupported: str | None = None

    def say(self, text: Any) -> None:
        self.log.append(str(text)[:300])

    # ------------------------------------------------------------------ crypto
    def _product(self, symbol: Any) -> str | None:
        return product_id(symbol)

    def _last_close(self, product: str, granularity: str = QUOTE_GRANULARITY) -> float | None:
        seconds = GRANULARITY_SECONDS[granularity]
        series = self._data.crypto_series(product, granularity, self._t - 3 * seconds)
        if series is None:
            return None
        index = series.closed_index(self._t)
        return None if index < 0 else series.candles[index]["close"]

    def bars(self, symbol, interval="1h", limit=60, asset_class="crypto", venue="coinbase"):
        if str(asset_class) != "crypto":
            return []
        granularity = INTERVALS.get(str(interval))
        if granularity is None:
            raise ValueError(f"coinbase: unsupported interval {interval!r}")
        product = self._product(symbol)
        if product is None:
            raise ValueError(f"coinbase: not a product id: {symbol!r}")
        count = max(1, int(limit))
        seconds = GRANULARITY_SECONDS[granularity]
        series = self._data.crypto_series(product, granularity, self._t - (count + 2) * seconds)
        if series is None:
            return []
        index = series.closed_index(self._t)
        if index < 0:
            return []
        out = []
        for candle in series.candles[max(0, index + 1 - count) : index + 1]:
            start = candle["ts"]
            out.append(
                {
                    "instrument": {"asset_class": "crypto", "symbol": product, "venue": "coinbase"},
                    "time": iso(start),
                    "start": iso(start),
                    "end": iso(start + seconds),
                    "open": _text_number(candle["open"]),
                    "high": _text_number(candle["high"]),
                    "low": _text_number(candle["low"]),
                    "close": _text_number(candle["close"]),
                    "volume": _text_number(candle.get("volume") or 0.0),
                }
            )
        return out

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        if str(asset_class) == "event":
            market = self._data.markets.get(str(symbol or "").upper())
            if market is None or not market.is_open(self._t):
                return None
            row = market.view(self._t)
            return {
                "instrument": {"asset_class": "event", "symbol": market.ticker, "venue": "kalshi"},
                "bid": None if row["yes_bid"] is None else format(row["yes_bid"], "f"),
                "ask": None if row["yes_ask"] is None else format(row["yes_ask"], "f"),
                "last": None if row["last_price"] is None else format(row["last_price"], "f"),
                "as_of": iso(self._t),
                "source": "backtest:kalshi",
                "delayed": False,
            }
        if str(asset_class) != "crypto":
            return None
        product = self._product(symbol)
        close = self._last_close(product) if product else None
        if close is None:
            return None
        return {
            "instrument": {"asset_class": "crypto", "symbol": product, "venue": "coinbase"},
            "bid": _text_number(close * (1.0 - self._half_spread)),
            "ask": _text_number(close * (1.0 + self._half_spread)),
            "last": _text_number(close),
            "as_of": iso(self._t),
            "source": "backtest:coinbase",
            "delayed": False,
        }

    def products(self, limit=25, quote="USD", min_volume_usd=250000.0):
        universe = list(self._products or DEFAULT_PRODUCTS)
        out = []
        for product in universe:
            if not str(product).upper().endswith("-" + str(quote).upper()):
                continue
            series = self._data.crypto_series(product, "ONE_HOUR", self._t - 26 * 3600)
            if series is None:
                continue
            index = series.closed_index(self._t)
            if index < 0:
                continue
            price = series.candles[index]["close"]
            volume = 0.0
            back = index
            while back >= 0 and series.starts[back] + 3600 > self._t - 86400:
                candle = series.candles[back]
                volume += (candle.get("volume") or 0.0) * candle["close"]
                back -= 1
            if price <= 0 or volume < float(min_volume_usd):
                continue
            out.append({"symbol": product, "price": price, "volume_usd": volume})
        out.sort(key=lambda r: -r["volume_usd"])
        return out[: int(limit)]

    def futures(self, root=None):
        self._data.note_once("futures", "kit.futures() has no history here and returned no contracts")
        return []

    # ------------------------------------------------------------------ kalshi
    def kalshi_markets(self, max_close_hours=36, pages=5):
        if not self._data.board:
            self._data.note_once("board", "kit.kalshi_markets() read only the loaded series; pass no series to load the board")
        until = self._t + float(max_close_hours) * 3600.0
        rows = [m.view(self._t) for m in self._data.open_markets(self._t, max_close=until)]
        return rows[: max(1, int(pages)) * 1000]

    def kalshi_market(self, ticker):
        market = self._data.markets.get(str(ticker or "").strip().upper())
        if market is None or not market.is_open(self._t):
            return None
        return market.view(self._t)

    def kalshi_series(self, series, limit=1000, status="open"):
        if status not in (None, "open", "active"):
            return []
        name = str(series or "").upper().split("-")[0]
        if not self._data.board and name not in self._data.loaded_series:
            self._data.note_once(f"series-{name}", f"kit.kalshi_series({name}) asked for a series that was not loaded; add it to spec.series")
            return []
        rows = [m.view(self._t) for m in self._data.open_markets(self._t, series=name)]
        return rows[: max(1, min(int(limit), 1000))]

    # ----------------------------------------------------------------- weather
    def weather(self, city):
        self.unsupported = "family weather is not backtestable: there is no history of NWS forecasts"
        raise Unsupported(self.unsupported)

    def weather_cities(self):
        self.unsupported = "family weather is not backtestable: there is no history of NWS forecasts"
        raise Unsupported(self.unsupported)


# ------------------------------------------------------------------------ simulator


class Simulator:
    """A conservative book: orders, fills, positions, settlements and closed-trade P&L."""

    def __init__(self, data: DataSet, *, strategy: str, learning_usd: float, half_spread: float, maker_fee: float, taker_fee: float, fill_model: str = "conservative"):
        self.data = data
        self.fill_model = fill_model if fill_model in FILL_MODELS else "conservative"
        self.strategy = strategy
        self.learning_usd = float(learning_usd)
        self.half_spread = half_spread
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.fills: list[dict[str, Any]] = []
        self.closed: list[dict[str, Any]] = []
        self.counts = {"orders": 0, "rejected": 0, "cancelled": 0, "expired": 0, "settled": 0, "exits": 0}
        self.reasons: dict[str, int] = {}
        self._next_id = 0

    # --------------------------------------------------------------- views
    def context(self, t: float) -> dict[str, Any]:
        positions = []
        for position in self.positions.values():
            quantity = position["quantity"]
            positions.append(
                {
                    "symbol": position["symbol"],
                    "market_id": position["market_id"],
                    "right": position["right"],
                    "asset_class": position["asset_class"],
                    "quantity": str(int(round(quantity))) if position["asset_class"] == "event" else _text_number(round(quantity, 8)),
                    "average_cost": _text_number(round(position["cost"] / quantity, 8)) if quantity > 0 else "",
                }
            )
        orders = []
        for order in self.orders.values():
            orders.append(
                {
                    "order_id": order["order_id"],
                    "intent_id": order["order_id"],
                    "market_id": order["market_id"],
                    "symbol": order["symbol"],
                    "right": order["right"],
                    "asset_class": order["asset_class"],
                    "venue": "kalshi" if order["asset_class"] == "event" else "coinbase",
                    "purpose": "entry",
                    "side": order["side"],
                    "quantity": order["quantity_text"],
                    "limit_price": order["price_text"],
                    "submitted_at": iso(order["submitted_ts"]),
                    "status": "open",
                    "strategy": order["strategy"],
                }
            )
        return {
            "now": iso(t),
            "desk_id": "backtest",
            "live": False,
            "learning_usd": _text_number(self.learning_usd),
            "positions": positions,
            "open_orders": orders,
            "venues": ["kalshi", "coinbase"],
            "dry_run": False,
            "backtest": True,
        }

    def _reject(self, reason: str) -> None:
        self.counts["rejected"] += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    # --------------------------------------------------------------- orders
    def cancel(self, order_ids: Iterable[Any], strategy: str) -> int:
        done = 0
        for order_id in list(order_ids)[:MAX_CANCELS_PER_RUN]:
            order = self.orders.get(str(order_id))
            if order is None or order["strategy"] != strategy:
                continue  # only the strategy's own resting orders
            del self.orders[str(order_id)]
            self.counts["cancelled"] += 1
            done += 1
        return done

    def add_order(self, order: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        order.setdefault("order_id", f"bt-{self._next_id}")
        self.orders[order["order_id"]] = order
        return order

    def submit(self, intent: Mapping[str, Any], t: float) -> str:
        """Book one intent at t. Returns what happened: filled, resting or rejected:<why>."""
        if not isinstance(intent, Mapping):
            self._reject("not an object")
            return "rejected:not an object"
        instrument = intent.get("instrument") if isinstance(intent.get("instrument"), Mapping) else {}
        asset_class = str(instrument.get("asset_class") or "")
        side = str(intent.get("side") or "")
        if str(intent.get("order_type") or "limit") != "limit":
            return self._refuse("a strategy proposes limit orders")
        if side not in ("buy", "sell"):
            return self._refuse("side must be buy or sell")
        price = _num(intent.get("limit_price"))
        quantity = _num(intent.get("quantity"))
        if price is None or price <= 0:
            return self._refuse("no usable limit_price")
        if quantity is None or quantity <= 0:
            return self._refuse("no usable quantity")
        post_only = bool(intent.get("post_only"))
        plan = self._plan(intent, t)
        if asset_class == "event":
            return self._submit_event(instrument, side, price, quantity, post_only, plan, t)
        if asset_class == "crypto":
            return self._submit_crypto(instrument, side, price, quantity, post_only, plan, t)
        return self._refuse(f"asset class {asset_class or 'missing'} is not simulated")

    def _refuse(self, reason: str) -> str:
        self._reject(reason)
        return "rejected:" + reason

    @staticmethod
    def _plan(intent: Mapping[str, Any], t: float) -> dict[str, Any] | None:
        holding = intent.get("holding_period_hours")
        stop = _num(intent.get("stop_price"))
        target = _num(intent.get("target_price"))
        time_stop = None
        if isinstance(holding, int) and not isinstance(holding, bool) and 1 <= holding <= 720:
            time_stop = t + holding * 3600.0
        if stop is None and target is None and time_stop is None:
            return None
        return {"stop": stop, "target": target, "time_stop": time_stop}

    def _submit_event(self, instrument, side, price, quantity, post_only, plan, t) -> str:
        ticker = str(instrument.get("market_id") or instrument.get("symbol") or "").upper()
        right = str(instrument.get("right") or "yes").lower()
        if right not in ("yes", "no"):
            return self._refuse("right must be yes or no")
        market = self.data.markets.get(ticker)
        if market is None:
            return self._refuse("market not in the loaded history")
        if not market.is_open(t):
            return self._refuse("market not open")
        if price >= 1.0:
            return self._refuse("event price must be under 1")
        contracts = math.floor(quantity + EPS)
        cap = math.floor(NOTIONAL_CAP_MULTIPLE * self.learning_usd / price + EPS)
        contracts = min(contracts, max(1, cap))
        if contracts < 1:
            return self._refuse("under one contract")
        key = ("event", ticker, right)
        if side == "sell":
            held = self.positions.get(key, {}).get("quantity", 0.0)
            resting = sum(o["quantity"] for o in self.orders.values() if o["asset_class"] == "event" and o["market_id"] == ticker and o["right"] == right and o["side"] == "sell")
            contracts = min(contracts, int(round(held - resting)))
            if contracts < 1:
                return self._refuse("sell of a leg not held")
        yes_bid, yes_ask = market.book(t)
        if side == "buy":
            touch = yes_ask if right == "yes" else (None if yes_bid is None else 1.0 - yes_bid)
            crosses = touch is not None and 0.0 < touch < 1.0 and price >= touch - EPS
        else:
            touch = yes_bid if right == "yes" else (None if yes_ask is None else 1.0 - yes_ask)
            crosses = touch is not None and 0.0 < touch < 1.0 and price <= touch + EPS
        if crosses and post_only:
            return self._refuse("post-only order would cross")
        self.counts["orders"] += 1
        if crosses:
            fill_price = round(touch, 4)
            self._fill_event(market, right, side, contracts, fill_price, kalshi_taker_fee(fill_price) * contracts, False, t, plan)
            return "filled"
        self.data.request_refine(market, t)
        order = self.add_order(
            {
                "strategy": self.strategy,
                "asset_class": "event",
                "market_id": ticker,
                "symbol": ticker,
                "right": right,
                "side": side,
                "quantity": contracts,
                "quantity_text": str(contracts),
                "price": price,
                "price_text": f"{price:.2f}" if abs(price * 100 - round(price * 100)) < 1e-6 else _text_number(price),
                "submitted_ts": t,
                "checked_ts": t,
                "plan": plan,
            }
        )
        return "resting:" + order["order_id"]

    def _submit_crypto(self, instrument, side, price, quantity, post_only, plan, t) -> str:
        product = product_id(instrument.get("symbol") or instrument.get("market_id"))
        if product is None:
            return self._refuse("not a product id")
        series = self.data.crypto_series(product, QUOTE_GRANULARITY, t - 3 * GRANULARITY_SECONDS[QUOTE_GRANULARITY])
        index = series.closed_index(t) if series is not None else -1
        if series is None or index < 0:
            return self._refuse("no price for the product")
        close = series.candles[index]["close"]
        cap = NOTIONAL_CAP_MULTIPLE * self.learning_usd / price
        quantity = min(quantity, cap)
        key = ("crypto", product, "")
        if side == "sell":
            held = self.positions.get(key, {}).get("quantity", 0.0)
            resting = sum(o["quantity"] for o in self.orders.values() if o["asset_class"] == "crypto" and o["symbol"] == product and o["side"] == "sell")
            quantity = min(quantity, held - resting)
            if quantity <= EPS:
                return self._refuse("sell of a coin not held")
        bid, ask = close * (1.0 - self.half_spread), close * (1.0 + self.half_spread)
        crosses = price >= ask - EPS if side == "buy" else price <= bid + EPS
        if crosses and post_only:
            return self._refuse("post-only order would cross")
        self.counts["orders"] += 1
        if crosses:
            fill_price = ask if side == "buy" else bid
            self._fill_crypto(product, side, quantity, fill_price, self.taker_fee, False, t, plan)
            return "filled"
        order = self.add_order(
            {
                "strategy": self.strategy,
                "asset_class": "crypto",
                "market_id": None,
                "symbol": product,
                "right": None,
                "side": side,
                "quantity": quantity,
                "quantity_text": _text_number(round(quantity, 8)),
                "price": price,
                "price_text": _text_number(price),
                "submitted_ts": t,
                "next_start": t,
                "plan": plan,
            }
        )
        return "resting:" + order["order_id"]

    # ---------------------------------------------------------------- fills
    def _position(self, key, *, symbol, market_id, right, asset_class, t) -> dict[str, Any]:
        position = self.positions.get(key)
        if position is None:
            position = self.positions[key] = {
                "symbol": symbol, "market_id": market_id, "right": right, "asset_class": asset_class,
                "quantity": 0.0, "cost": 0.0, "fees": 0.0, "realized": 0.0, "notional": 0.0,
                "opened_ts": t, "plan": None,
            }
        return position

    def _record_fill(self, **fill: Any) -> None:
        self.fills.append(fill)

    def _fill_event(self, market: Market, right: str, side: str, contracts: int, price: float, fee: float, maker: bool, t: float, plan) -> None:
        key = ("event", market.ticker, right)
        position = self._position(key, symbol=market.ticker, market_id=market.ticker, right=right, asset_class="event", t=t)
        self._apply(key, position, side, float(contracts), price, fee, t, plan)
        self._record_fill(ts=t, asset_class="event", symbol=market.ticker, right=right, side=side, quantity=float(contracts), price=price, fee=fee, maker=maker)

    def _fill_crypto(self, product: str, side: str, quantity: float, price: float, fee_rate: float, maker: bool, t: float, plan) -> None:
        key = ("crypto", product, "")
        position = self._position(key, symbol=product, market_id=None, right=None, asset_class="crypto", t=t)
        fee = quantity * price * fee_rate
        self._apply(key, position, side, quantity, price, fee, t, plan)
        self._record_fill(ts=t, asset_class="crypto", symbol=product, right=None, side=side, quantity=quantity, price=price, fee=fee, maker=maker)

    def _apply(self, key, position, side, quantity, price, fee, t, plan) -> None:
        position["fees"] += fee
        if side == "buy":
            position["quantity"] += quantity
            position["cost"] += quantity * price
            position["notional"] += quantity * price
            if plan is not None:
                position["plan"] = plan
            return
        held = position["quantity"]
        quantity = min(quantity, held)
        average = position["cost"] / held if held > 0 else 0.0
        position["realized"] += quantity * (price - average)
        position["cost"] -= quantity * average
        position["quantity"] -= quantity
        if position["quantity"] <= max(EPS, held * 1e-9):
            self._close(key, t, "sold")

    def _close(self, key, t: float, how: str) -> None:
        position = self.positions.pop(key, None)
        if position is None:
            return
        pnl = position["realized"] - position["fees"]
        self.closed.append(
            {"ts": t, "symbol": position["symbol"], "right": position["right"], "asset_class": position["asset_class"],
             "pnl": pnl, "notional": position["notional"], "how": how}
        )
        for order_id in [o["order_id"] for o in self.orders.values() if o["side"] == "sell" and o["symbol"] == position["symbol"] and o["right"] == position["right"]]:
            self.orders.pop(order_id, None)

    # ------------------------------------------------------------------ clock
    def advance(self, t: float) -> None:
        """Everything the venue would have done by t: resting fills, settlements, expiries, exits."""
        self.data.flush_refine()
        for order in sorted(list(self.orders.values()), key=lambda o: o["submitted_ts"]):
            if order["order_id"] not in self.orders:
                continue
            if order["asset_class"] == "event":
                self._check_event_order(order, t)
            else:
                self._check_crypto_order(order, t)
        for key in [k for k in self.positions if k[0] == "event"]:
            market = self.data.markets.get(key[1])
            if market is not None and t >= market.close_ts:
                self._settle(key, market)
        for order_id in [o["order_id"] for o in self.orders.values() if o["asset_class"] == "event"]:
            market = self.data.markets.get(self.orders[order_id]["market_id"])
            if market is None or t >= market.close_ts:
                del self.orders[order_id]
                self.counts["expired"] += 1
        self._exits(t)

    def _check_event_order(self, order: dict[str, Any], t: float) -> None:
        market = self.data.markets.get(order["market_id"])
        if market is None:
            return
        horizon = min(t, market.close_ts)
        index = bisect.bisect_right(market.ends, max(order["checked_ts"], order["submitted_ts"]))
        price, right, side = order["price"], order["right"], order["side"]
        touch = self.fill_model == "touch"

        def below(value: float | None, level: float) -> bool:
            return value is not None and value > 0.0 and (value <= level + EPS if touch else value < level - EPS)

        def above(value: float | None, level: float) -> bool:
            return value is not None and value > 0.0 and (value >= level - EPS if touch else value > level + EPS)

        while index < len(market.ends) and market.ends[index] <= horizon:
            candle = market.candles[index]
            started = market.ends[index] - market.periods[index]
            whole = started >= order["submitted_ts"] - EPS
            ask_low = candle.get("yes_ask_low" if whole else "yes_ask_close")
            bid_high = candle.get("yes_bid_high" if whole else "yes_bid_close")
            # Trade prints count only under "touch", and only from a candle wholly after the order.
            trade_low = candle.get("price_low") if touch and whole else None
            trade_high = candle.get("price_high") if touch and whole else None
            if side == "buy" and right == "yes":
                filled = below(ask_low, price) or below(trade_low, price)
            elif side == "buy":
                filled = above(bid_high, 1.0 - price) or above(trade_high, 1.0 - price)
            elif right == "yes":
                filled = above(bid_high, price) or above(trade_high, price)
            else:
                filled = below(ask_low, 1.0 - price) or below(trade_low, 1.0 - price)
            index += 1
            if filled:
                del self.orders[order["order_id"]]
                contracts = int(order["quantity"])
                if side == "sell":
                    contracts = min(contracts, int(round(self.positions.get(("event", market.ticker, right), {}).get("quantity", 0.0))))
                    if contracts < 1:
                        return
                self._fill_event(market, right, side, contracts, price, 0.0, True, float(market.ends[index - 1]), order.get("plan"))
                return
        if index > 0:
            order["checked_ts"] = max(order["checked_ts"], market.ends[index - 1])

    def _check_crypto_order(self, order: dict[str, Any], t: float) -> None:
        series = self.data.crypto_series(order["symbol"], QUOTE_GRANULARITY, order["submitted_ts"] - 3 * GRANULARITY_SECONDS[QUOTE_GRANULARITY])
        if series is None:
            return
        index = bisect.bisect_left(series.starts, order["next_start"])
        while index < len(series.starts) and series.starts[index] + series.seconds <= t:
            candle = series.candles[index]
            order["next_start"] = series.starts[index] + series.seconds
            touched = candle["low"] <= order["price"] + EPS if order["side"] == "buy" else candle["high"] >= order["price"] - EPS
            if touched:
                del self.orders[order["order_id"]]
                quantity = order["quantity"]
                if order["side"] == "sell":
                    quantity = min(quantity, self.positions.get(("crypto", order["symbol"], ""), {}).get("quantity", 0.0))
                    if quantity <= EPS:
                        return
                self._fill_crypto(order["symbol"], order["side"], quantity, order["price"], self.maker_fee, True, float(series.starts[index] + series.seconds), order.get("plan"))
                return
            index += 1

    def _settle(self, key, market: Market) -> None:
        position = self.positions.get(key)
        if position is None:
            return
        if market.payout_yes is None:
            payout = position["cost"] / position["quantity"] if position["quantity"] > 0 else 0.0
            self.data.note_once(f"void-{market.ticker}", f"{market.ticker} settled without a yes/no result; refunded at cost")
        else:
            payout = market.payout_yes if key[2] == "yes" else 1.0 - market.payout_yes
        position["realized"] += position["quantity"] * payout - position["cost"]
        position["cost"] = 0.0
        self.counts["settled"] += 1
        self._close(key, market.close_ts, "settled")

    def mark(self, key, position, t: float) -> float | None:
        """The exit-side price of a position at t (its bid), or None."""
        if key[0] == "event":
            market = self.data.markets.get(key[1])
            if market is None:
                return None
            yes_bid, yes_ask = market.book(t)
            bid = yes_bid if key[2] == "yes" else (None if yes_ask is None else 1.0 - yes_ask)
            return bid if bid is not None and bid > 0 else None
        series = self.data.crypto_series(key[1], QUOTE_GRANULARITY, t - 3 * GRANULARITY_SECONDS[QUOTE_GRANULARITY])
        index = series.closed_index(t) if series is not None else -1
        return None if index < 0 else series.candles[index]["close"] * (1.0 - self.half_spread)

    def _exits(self, t: float) -> None:
        for key in list(self.positions):
            position = self.positions.get(key)
            plan = position.get("plan") if position else None
            if not plan:
                continue
            if key[0] == "event":
                market = self.data.markets.get(key[1])
                if market is None or not market.is_open(t):
                    continue
            mark = self.mark(key, position, t)
            reason = None
            if mark is not None and plan.get("stop") is not None and mark <= plan["stop"] + EPS:
                reason = "stop"
            elif mark is not None and plan.get("target") is not None and mark >= plan["target"] - EPS:
                reason = "target"
            elif key[0] != "event" and plan.get("time_stop") is not None and t >= plan["time_stop"]:
                reason = "time_stop"
            if reason is None or mark is None:
                continue
            self.counts["exits"] += 1
            quantity = position["quantity"]
            if key[0] == "event":
                market = self.data.markets[key[1]]
                self._fill_event(market, key[2], "sell", int(round(quantity)), round(mark, 4), kalshi_taker_fee(round(mark, 4)) * int(round(quantity)), False, t, None)
            else:
                self._fill_crypto(key[1], "sell", quantity, mark, self.taker_fee, False, t, None)

    def finish(self, t: float) -> dict[str, float]:
        """Settle what closed by t and mark the rest at its bid. Returns the unrealized P&L."""
        self.advance(t)
        unrealized = 0.0
        marked = 0
        for key, position in list(self.positions.items()):
            mark = self.mark(key, position, t)
            if mark is None:
                mark = position["cost"] / position["quantity"] if position["quantity"] > 0 else 0.0
            unrealized += position["quantity"] * mark - position["cost"] + position["realized"] - position["fees"]
            marked += 1
        return {"unrealized": unrealized, "open_positions": marked}


# -------------------------------------------------------------------------- metrics


def bootstrap_ci(values: list[float], seed: Any = 7, resamples: int = BOOTSTRAP_RESAMPLES) -> list[float | None]:
    """A deterministic 95% bootstrap interval for the mean of `values`."""
    if not values:
        return [None, None]
    if len(values) == 1:
        return [round(values[0], 4), round(values[0], 4)]
    rng = random.Random(str(seed))
    n = len(values)
    means = sorted(math.fsum(rng.choices(values, k=n)) / n for _ in range(int(resamples)))
    lo = means[max(0, int(math.floor(0.025 * len(means))))]
    hi = means[min(len(means) - 1, int(math.ceil(0.975 * len(means))) - 1)]
    return [round(lo, 4), round(hi, 4)]


def max_drawdown(pnls: Iterable[float]) -> float:
    peak = equity = worst = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return round(worst, 4)


def split_report(report: Mapping[str, Any], fraction: float = 0.66) -> dict[str, Any]:
    """The closed trades split chronologically: the first `fraction` in sample, the rest out."""
    pnls = [float(x) for x in (report.get("trade_pnls") or [])]
    notionals = [float(x) for x in (report.get("trade_notionals") or [])]
    if len(notionals) != len(pnls):
        notionals = []
    cut = int(round(len(pnls) * min(1.0, max(0.0, float(fraction)))))
    seed = report.get("seed", 7)

    def part(values: list[float], spent: list[float]) -> dict[str, Any]:
        total = math.fsum(values)
        notional = math.fsum(spent) if spent else 0.0
        return {
            "trades": len(values),
            "pnl_usd": round(total, 4),
            "return_on_notional": round(total / notional, 4) if notional > 0 else None,
            "ci95_mean_pnl": bootstrap_ci(values, seed),
        }

    return {
        "in_sample": part(pnls[:cut], notionals[:cut]),
        "out_of_sample": part(pnls[cut:], notionals[cut:]),
    }


# ----------------------------------------------------------------------------- run


def _empty_report(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy": spec.get("strategy"),
        "params": spec.get("params") if isinstance(spec.get("params"), dict) else {},
        "start": spec.get("start"),
        "end": spec.get("end"),
        "steps": 0,
        "trades": 0,
        "fills": 0,
        "settled": 0,
        "wins": 0,
        "notional_usd": 0.0,
        "pnl_usd": 0.0,
        "fees_usd": 0.0,
        "return_on_notional": None,
        "max_drawdown_usd": 0.0,
        "daily": [],
        "trade_pnls": [],
        "ci95_mean_pnl": [None, None],
        "errors": 0,
        "notes": [],
    }


def _load_code(spec: Mapping[str, Any]) -> str:
    code = spec.get("code")
    if isinstance(code, str) and code.strip():
        return code
    name = str(spec.get("strategy") or "")
    if not re.match(r"^[a-z][a-z0-9_]{0,39}$", name):
        raise ValueError("spec.strategy must name a starter (lowercase letters, digits, underscores) or spec.code must carry the source")
    path = STARTERS_DIR / f"{name}.py"
    if not path.exists():
        raise ValueError(f"no code given and no starter named {name}")
    return path.read_text(encoding="utf-8")


def kalshi_plan(code: str, params: Mapping[str, Any], spec: Mapping[str, Any], namespace: Mapping[str, Any]) -> tuple[str, list[str]]:
    """What Kalshi history a strategy needs: ("board", []), ("series", [...]) or ("none", [])."""
    wanted = spec.get("series")
    if isinstance(wanted, str):
        wanted = [wanted]
    if wanted:
        return "series", sorted({str(s).upper() for s in wanted})
    if "kalshi_markets" in code:
        return "board", []
    if "kalshi_series" not in code and "kalshi_market" not in code:
        return "none", []
    defaults = namespace.get("DEFAULTS") if isinstance(namespace.get("DEFAULTS"), Mapping) else {}
    pick = params.get("series") if "series" in params else defaults.get("series")
    catalogue = namespace.get("CRYPTO_SERIES") if isinstance(namespace.get("CRYPTO_SERIES"), Mapping) else None
    if (pick == "all" or pick is None) and catalogue:
        return "series", sorted(str(s).upper() for s in catalogue)
    if isinstance(pick, str) and pick != "all":
        return "series", [pick.upper()]
    if isinstance(pick, (list, tuple)) and pick:
        return "series", sorted({str(s).upper() for s in pick})
    literals = sorted({m.group(1) for m in SERIES_LITERAL.finditer(code)})
    if literals:
        return "series", literals
    return "board", []


def run_backtest(spec: Mapping[str, Any], *, history: Any = None) -> dict[str, Any]:
    """Replay `spec["strategy"]` over [start, end]; see the module docstring for the rules."""
    began = time.monotonic()
    spec = {**DEFAULT_SPEC, **dict(spec or {})}
    report = _empty_report(spec)
    notes: list[str] = report["notes"]

    def say(text: str) -> None:
        if not spec.get("verbose", True):
            return
        try:
            print(f"[backtest] {text}", file=sys.stderr, flush=True)
        except Exception:
            pass

    try:
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        params = json.loads(json.dumps(params, default=str))
        start_ts = parse_time(spec.get("start"))
        end_ts = parse_time(spec.get("end"))
        step = int(round(float(spec.get("step_minutes") or 15) * 60))
        if end_ts <= start_ts:
            raise ValueError("end must be after start")
        if step < 60:
            raise ValueError("step_minutes must be at least 1")
        learning = float(_num(spec.get("learning_usd"), 10.0) or 10.0)
        fill_model = str(spec.get("fill_model") or "conservative")
        if fill_model not in FILL_MODELS:
            notes.append(f"fill_model {fill_model} is not known; conservative used")
            fill_model = "conservative"
        code = _load_code(spec)
        name = str(spec.get("strategy") or "strategy")
        compiled = compile(code, f"strategy:{name}", "exec")
    except Exception as exc:
        report["errors"] = 1
        report["notes"].append(_clean(f"spec refused: {type(exc).__name__}: {exc}"))
        return report
    report["start"], report["end"] = iso(start_ts), iso(end_ts)
    report["params"] = params
    report["seed"] = spec.get("seed", 7)

    namespace: dict[str, Any] = {"__name__": f"backtest_{name}"}
    try:
        with contextlib.redirect_stdout(sys.stderr):
            exec(compiled, namespace)
        if not callable(namespace.get("decide")):
            raise ValueError("the code defines no decide(kit, params)")
    except Exception as exc:
        report["errors"] = 1
        notes.append(_clean(f"strategy did not load: {type(exc).__name__}: {exc}"))
        return report

    if history is None:
        from .history import History

        history = History(cache_dir=spec.get("cache_dir") or _default_cache_dir())
    data = DataSet(history, start_ts, end_ts, say=say, notes=notes)
    mode, series = kalshi_plan(code, params, spec, namespace)
    if "weather" in code:
        # A strategy that reads forecasts cannot be replayed; find out before loading anything.
        probe_data = DataSet(_NoHistory(), start_ts, end_ts, say=say, notes=[])
        probe = BacktestKit(probe_data, Simulator(probe_data, strategy=name, learning_usd=learning, half_spread=0.0, maker_fee=0.0, taker_fee=0.0), start_ts, products=[], half_spread=0.0)
        try:
            probe_ns = {"__name__": f"backtest_{name}"}
            with contextlib.redirect_stdout(sys.stderr):
                exec(compiled, probe_ns)
                probe_ns["decide"](probe, copy.deepcopy(params))
        except Exception:
            pass
        if probe.unsupported:
            report["unsupported"] = probe.unsupported
            notes.append(_clean(probe.unsupported))
            report["runtime_seconds"] = round(time.monotonic() - began, 1)
            return report
    try:
        if mode != "none":
            data.load_kalshi(
                series=series,
                board=(mode == "board"),
                max_markets=int(spec.get("max_markets") or 3000),
                min_volume=_num(spec.get("min_volume")),
                max_pages=int(spec.get("max_pages") or (50 if mode == "board" else 20)),
            )
    except Exception as exc:
        data.errors += 1
        notes.append(_clean(f"kalshi history failed: {type(exc).__name__}: {exc}"))
    if mode == "series":
        notes.append("series loaded: " + ", ".join(series))
    elif mode == "board":
        notes.append("the settled board was loaded")

    half_spread = float(_num(spec.get("half_spread_bps"), 1.0) or 0.0) / 10_000.0
    products = spec.get("products")
    if isinstance(products, str):
        products = [products]
    products = [str(p).upper() for p in products] if isinstance(products, (list, tuple)) and products else None
    sim = Simulator(
        data,
        strategy=name,
        learning_usd=learning,
        half_spread=half_spread,
        maker_fee=float(_num(spec.get("coinbase_maker_fee"), 0.0025)),
        taker_fee=float(_num(spec.get("coinbase_taker_fee"), 0.006)),
        fill_model=fill_model,
    )
    budget = float(_num(spec.get("max_seconds"), 0.0) or 0.0)
    errors = 0
    first_errors: list[str] = []
    steps = 0
    total_steps = int((end_ts - start_ts) // step) + 1
    last_said = time.monotonic()
    t = start_ts
    stopped_at = None
    while t <= end_ts + EPS:
        sim.advance(t)
        kit = BacktestKit(data, sim, t, products=products, half_spread=half_spread)
        run_ns = {"__name__": f"backtest_{name}"}
        out: Any = None
        try:
            with contextlib.redirect_stdout(sys.stderr):
                exec(compiled, run_ns)  # a fresh module each run, as each floor run is a fresh process
                out = run_ns["decide"](kit, copy.deepcopy(params))
        except Unsupported:
            pass
        except Exception as exc:
            errors += 1
            if len(first_errors) < 3:
                first_errors.append(f"{iso(t)} {type(exc).__name__}: {str(exc)[:160]}")
        steps += 1
        if kit.unsupported:
            report["unsupported"] = kit.unsupported
            notes.append(_clean(f"stopped at {iso(t)}: {kit.unsupported}"))
            break
        intents: list[Any] = []
        cancels: list[Any] = []
        if isinstance(out, dict):
            intents = list(out.get("intents") or [])
            cancels = [c for c in (out.get("cancels") or []) if isinstance(c, str)]
        elif isinstance(out, (list, tuple)):
            intents = list(out)
        if cancels:
            sim.cancel(cancels, name)
        for intent in [i for i in intents if isinstance(i, dict)][:MAX_INTENTS_PER_RUN]:
            try:
                sim.submit(intent, t)
            except Exception as exc:
                errors += 1
                if len(first_errors) < 3:
                    first_errors.append(f"{iso(t)} booking {type(exc).__name__}: {str(exc)[:160]}")
        if time.monotonic() - last_said > 20:
            last_said = time.monotonic()
            say(f"{iso(t)}: step {steps}/{total_steps}, {len(sim.fills)} fills, {len(sim.closed)} closed")
        if budget and time.monotonic() - began > budget:
            stopped_at = t
            notes.append(f"time budget of {budget:.0f}s reached at {iso(t)}; the report covers the window up to there")
            break
        t += step
    finish_at = min(end_ts, stopped_at) if stopped_at is not None else end_ts
    marks = sim.finish(finish_at)

    closed = sorted(sim.closed, key=lambda c: c["ts"])
    pnls = [round(c["pnl"], 4) for c in closed]
    realized = math.fsum(c["pnl"] for c in closed)
    fees = math.fsum(f["fee"] for f in sim.fills)
    notional = math.fsum(f["quantity"] * f["price"] for f in sim.fills if f["side"] == "buy")
    pnl = realized + marks["unrealized"]
    days: dict[str, dict[str, Any]] = {}
    day_ts = math.floor(start_ts / 86400) * 86400
    while day_ts <= finish_at:
        days[_day(day_ts)] = {"day": _day(day_ts), "pnl_usd": 0.0, "trades": 0}
        day_ts += 86400
    for trade in closed:
        row = days.setdefault(_day(trade["ts"]), {"day": _day(trade["ts"]), "pnl_usd": 0.0, "trades": 0})
        row["pnl_usd"] += trade["pnl"]
        row["trades"] += 1
    for row in days.values():
        row["pnl_usd"] = round(row["pnl_usd"], 4)
    report.update(
        steps=steps,
        trades=len(closed),
        fills=len(sim.fills),
        settled=sim.counts["settled"],
        wins=sum(1 for c in closed if c["pnl"] > 0),
        notional_usd=round(notional, 4),
        pnl_usd=round(pnl, 4),
        realized_pnl_usd=round(realized, 4),
        unrealized_pnl_usd=round(marks["unrealized"], 4),
        open_positions=marks["open_positions"],
        fees_usd=round(fees, 4),
        return_on_notional=round(pnl / notional, 4) if notional > 0 else None,
        max_drawdown_usd=max_drawdown(pnls),
        daily=[days[k] for k in sorted(days)],
        trade_pnls=pnls,
        trade_notionals=[round(c["notional"], 4) for c in closed],
        ci95_mean_pnl=bootstrap_ci(pnls, spec.get("seed", 7)),
        errors=errors + data.errors,
        orders=sim.counts["orders"],
        rejected=sim.counts["rejected"],
        cancelled=sim.counts["cancelled"],
        expired=sim.counts["expired"],
        exits=sim.counts["exits"],
        maker_fills=sum(1 for f in sim.fills if f["maker"]),
        markets_loaded=len(data.markets),
        markets_priced=sum(1 for m in data.markets.values() if m.candles),
        markets_refined=len(data.refined),
        http_requests=int(getattr(history, "requests", 0) or 0),
        cache_hits=int(getattr(history, "cache_hits", 0) or 0),
        runtime_seconds=round(time.monotonic() - began, 1),
        fill_model=fill_model,
    )
    for text in first_errors:
        notes.append(_clean("strategy error " + text))
    if sim.reasons:
        top = sorted(sim.reasons.items(), key=lambda kv: -kv[1])[:4]
        notes.append(_clean("rejected intents: " + "; ".join(f"{k} x{v}" for k, v in top)))
    report["notes"] = [_clean(n) for n in notes][:24]
    say(f"done in {report['runtime_seconds']}s: {report['trades']} trades, pnl {report['pnl_usd']}, {report['http_requests']} requests")
    return report


class _NoHistory:
    """History that has nothing: the probe run that looks for unsupported kit calls."""

    requests = 0

    def kalshi_settled(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def kalshi_candles(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def coinbase_candles(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


def _default_cache_dir() -> str | None:
    configured = os.environ.get("LTCM_HISTORY_CACHE")
    if configured:
        return configured
    if Path("/lab/cache").is_dir():
        return "/lab/cache/history"
    return None


def main(argv: list[str] | None = None) -> int:
    """`python3 -m ltcm.backtest --spec FILE` (or the spec on stdin): one BACKTEST-RESULT line."""
    parser = argparse.ArgumentParser(prog="python3 -m ltcm.backtest", add_help=False)
    parser.add_argument("--spec", help="a JSON spec file; without it the spec is read from stdin")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        report = _empty_report({})
        report["errors"] = 1
        report["notes"].append("usage: python3 -m ltcm.backtest --spec FILE (or the spec as JSON on stdin)")
        print(RESULT_PREFIX + json.dumps(report, default=str), flush=True)
        return 0
    spec: Any = {}
    try:
        raw = Path(args.spec).read_text(encoding="utf-8") if args.spec else sys.stdin.read()
        spec = json.loads(raw)
        if not isinstance(spec, dict):
            raise ValueError("the spec is not a JSON object")
    except Exception as exc:
        report = _empty_report({})
        report["errors"] = 1
        report["notes"].append(_clean(f"spec unreadable: {type(exc).__name__}: {exc}"))
        print(RESULT_PREFIX + json.dumps(report, default=str), flush=True)
        return 0
    try:
        report = run_backtest(spec)
    except Exception as exc:  # the caller reads a report, never a bare traceback
        report = _empty_report(spec)
        report["errors"] = 1
        report["notes"].append(_clean(f"backtest failed: {type(exc).__name__}: {exc}"))
        tail = traceback.format_exc().strip().splitlines()[-3:]
        report["notes"].extend(_clean(line, 200) for line in tail)
    print(RESULT_PREFIX + json.dumps(report, default=str), flush=True)
    return 0


__all__ = [
    "BacktestKit",
    "DataSet",
    "Market",
    "Simulator",
    "Unsupported",
    "bootstrap_ci",
    "kalshi_plan",
    "kalshi_taker_fee",
    "main",
    "max_drawdown",
    "run_backtest",
    "split_report",
]


if __name__ == "__main__":
    sys.exit(main())

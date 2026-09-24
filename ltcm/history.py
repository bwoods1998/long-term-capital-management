"""History: settled Kalshi markets, their candlesticks, and Coinbase candles, for backtests.

The floor's data sources read the market as it is now; a backtest needs it as it was. This
module reads the public history both venues keep and hands it back in plain rows the backtest
engine (`ltcm/backtest.py`) replays against a strategy:

    GET https://api.elections.kalshi.com/trade-api/v2/markets?status=settled&series_ticker=&min_close_ts=&max_close_ts=&mve_filter=exclude
    GET https://api.elections.kalshi.com/trade-api/v2/series/{series}/markets/{ticker}/candlesticks?start_ts=&end_ts=&period_interval=1|60|1440
    GET https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=a,b,...&start_ts=&end_ts=&period_interval=
        (at most 100 markets and 10,000 candlesticks counted as markets x periods, else HTTP 400)
    GET https://api.coinbase.com/api/v3/brokerage/market/products/{id}/candles?start=&end=&granularity=
        (fewer than 350 candles a call; 300 are asked for)

Kalshi's minute candlesticks are sparse: a minute in which nothing changed has no candle, so a
reader carries the last candle forward. Settled data does not change, so responses whose window
lies safely in the past are kept in an on-disk cache with a hard byte cap (oldest evicted first):
an uncapped cache filled a 32 GB floor disk on Sept 16, 2026, and nothing here may repeat that.

Standard library only; importable in a desk's sandbox (`FLOOR_EXTRAS`). Requests are throttled
per host (`min_interval`, 0.15 s: under seven a second) and retried with backoff on 429 and 5xx.
Progress goes to stderr, never stdout.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import sys
import threading
import time
import urllib.parse
import zlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

try:  # POSIX; elsewhere the cache measures its directory on every put
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.coinbase.com/api/v3/brokerage/market"

#: Coinbase's granularity enum -> seconds per candle.
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
COINBASE_CHUNK = 300
#: Kalshi's batch candlestick limits (verified Sept 16, 2026 from its 400 responses).
BATCH_MARKETS = 100
BATCH_CANDLES = 10_000
#: The single-market endpoint is asked for no more periods than this per call.
SINGLE_PERIODS = 4_000
#: A response is cached only when its window ended at least this long ago: a settled listing can
#: still grow while recent markets finalize, and the newest candle can still be moving.
LISTING_SETTLE_SECONDS = 12 * 3600
CANDLE_SETTLE_SECONDS = 3600
#: Retries of a 429 or 5xx, backing off 1, 2, 4 ... 30 seconds: about five minutes in all. The
#: public limit is per address, so another reader on the same machine can spend it for us.
MAX_RETRIES = 12


class HistoryError(RuntimeError):
    """A history read failed after its retries."""


class HistoryTimeout(HistoryError):
    """A read was not started, or its retries were abandoned, because `History.deadline` passed."""


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _log(text: str) -> None:
    try:
        print(f"[history] {text}", file=sys.stderr, flush=True)
    except Exception:
        pass


class DiskCache:
    """Compressed response bodies keyed by URL, never larger than `cap_bytes` on disk.

    The cap holds for every process and thread sharing the directory, not only this instance:
    four backtests on one cache directory once each counted only their own writes and together
    held four times the cap. A put takes an exclusive `flock` on the directory's `.lock` file,
    reads the byte count every writer keeps in `.bytes`, evicts the least recently used entries
    first when the new body would pass the cap, writes the body and the new count, and lets go.
    The count is measured from the directory again every `RESCAN_EVERY` puts and whenever it is
    missing, so a writer that died between the two writes cannot leave it wrong for long. Where
    `flock` is unavailable every put measures the directory itself."""

    RESCAN_EVERY = 32
    LOCK_NAME = ".lock"
    COUNT_NAME = ".bytes"

    def __init__(self, directory: str | Path, cap_bytes: int):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cap = max(1024, int(cap_bytes))
        self._lock = threading.Lock()
        self._puts = 0
        self._bytes = 0
        with self._exclusive():
            for stray in self.dir.glob("*.tmp"):
                try:
                    stray.unlink()  # every writer holds the lock while its temp file exists
                except OSError:
                    pass
            total = self._measure()
            if total > self.cap:
                total = self._evict(int(self.cap * 0.9))
            self._store_count(total)

    @contextlib.contextmanager
    def _exclusive(self):
        """This thread alone, and (where `flock` works) this process alone, on the directory.
        Yields whether other processes are shut out."""
        with self._lock:
            handle = None
            if fcntl is not None:
                try:
                    handle = open(self.dir / self.LOCK_NAME, "a+b")
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                except OSError:
                    if handle is not None:
                        handle.close()
                    handle = None
            try:
                yield handle is not None
            finally:
                if handle is not None:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                    handle.close()

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:40] + ".z")

    def _entries(self) -> list[tuple[float, int, Path]]:
        entries = []
        for path in self.dir.glob("*.z"):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        return entries

    def _measure(self) -> int:
        return sum(size for _, size, _ in self._entries())

    def _evict(self, target: int) -> int:
        """Remove the least recently used entries until the directory holds at most `target`
        bytes. Returns the bytes left."""
        entries = self._entries()
        total = sum(size for _, size, _ in entries)
        for _, size, path in sorted(entries):
            if total <= target:
                break
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue
            total -= size
        return total

    def _read_count(self) -> int | None:
        try:
            value = int((self.dir / self.COUNT_NAME).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
        return value if value >= 0 else None

    def _store_count(self, total: int) -> None:
        self._bytes = max(0, int(total))
        fresh = self.dir / (self.COUNT_NAME + ".new")
        try:
            fresh.write_text(str(self._bytes), encoding="ascii")
            fresh.replace(self.dir / self.COUNT_NAME)
        except OSError:
            pass

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        try:
            body = zlib.decompress(raw)
        except zlib.error:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            os.utime(path, None)  # recently read entries are evicted last
        except OSError:
            pass
        return body

    def put(self, key: str, body: bytes) -> None:
        packed = zlib.compress(body, 6)
        if len(packed) > self.cap // 8:
            return  # one entry never takes more than an eighth of the cap
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        with self._exclusive() as shared:
            self._puts += 1
            total = self._read_count() if shared else None
            if total is None or self._puts % self.RESCAN_EVERY == 0:
                total = self._measure()
            try:
                previous = path.stat().st_size
            except OSError:
                previous = 0
            if total - previous + len(packed) > self.cap:
                # Room first, then the write: the directory never holds more than the cap.
                total = self._evict(int(self.cap * 0.9) - len(packed))
                try:
                    previous = path.stat().st_size
                except OSError:
                    previous = 0
            try:
                tmp.write_bytes(packed)
                tmp.replace(path)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                self._store_count(total)
                return
            self._store_count(total - previous + len(packed))

    def trim(self) -> int:
        """Evict the least recently used entries until the cache is under nine tenths of its cap.
        Returns how many entries went."""
        with self._exclusive():
            before = len(self._entries())
            total = self._evict(int(self.cap * 0.9))
            self._store_count(total)
            return before - len(self._entries())

    def size(self) -> int:
        """The bytes on disk, as the last put or trim by any writer left them."""
        return self._bytes


class History:
    """Public venue history: settled Kalshi markets, Kalshi candlesticks, Coinbase candles."""

    def __init__(
        self,
        transport: Any = None,
        *,
        cache_dir: str | Path | None = None,
        # Sept 17, 2026: a ten-day board replay lists ~40 six-hour chunks of up to 20,000 markets;
        # at 128 MB the cache evicted the front of the window while reading the back, so every
        # cycle refetched. Two gigabytes holds a month of the board on a sandbox's 32 GB disk.
        cache_cap_bytes: int = 2 * 1024 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
        min_interval: float = 0.15,
        sleep: Callable[[float], None] = time.sleep,
        verbose: bool = True,
        max_retries: int = MAX_RETRIES,
        deadline: float | None = None,
        debug: bool = False,
    ):
        if transport is None:
            from .data import HttpTransport

            # A dense batch of 10,000 candlesticks is about 3.5 MB of JSON; leave headroom.
            transport = HttpTransport(min_interval=0.0, max_bytes=24 * 1024 * 1024)
        self.transport = transport
        self.cache = DiskCache(cache_dir, cache_cap_bytes) if cache_dir else None
        self.clock = clock
        self.min_interval = float(min_interval)
        self.sleep = sleep
        self.verbose = bool(verbose)
        #: Also say a listing the disk cache answered (one line; `kalshi_settled`).
        self.debug = bool(debug)
        self.max_retries = max(0, int(max_retries))
        #: A `time.monotonic()` moment after which no request starts and no retry waits: a caller
        #: with a wall-clock budget (a sandbox kills a run at its timeout, output and all) gets a
        #: `HistoryTimeout` it can report instead. None: no deadline.
        self.deadline = deadline
        self.requests = 0
        self.cache_hits = 0
        self.rate_limited = 0
        self.truncated_listings = 0
        self._next_at: dict[str, float] = {}
        #: Per host, how many times `min_interval` requests are spaced now. A 429 doubles it (the
        #: public limit is shared with whatever else runs from this address); successes ease it.
        self._slow: dict[str, float] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ http
    def _check_deadline(self, wait: float = 0.0) -> None:
        if self.deadline is not None and time.monotonic() + max(0.0, wait) > float(self.deadline):
            raise HistoryTimeout("the run's time budget is spent; no more history is read")

    def _throttle(self, url: str) -> None:
        if self.min_interval <= 0:
            return
        host = urllib.parse.urlsplit(url).netloc
        with self._lock:
            now = time.monotonic()
            wait = self._next_at.get(host, 0.0) - now
            if wait > 0:
                self.sleep(wait)
            self._next_at[host] = time.monotonic() + self.min_interval * self._slow.get(host, 1.0)

    def _pace(self, url: str, limited: bool) -> None:
        host = urllib.parse.urlsplit(url).netloc
        factor = self._slow.get(host, 1.0)
        self._slow[host] = min(16.0, factor * 2.0) if limited else max(1.0, factor * 0.9)

    def get_json(self, url: str, *, cacheable: bool = False) -> Any:
        """GET a JSON document, from the cache when allowed; retries 429 and 5xx with backoff."""
        return self._get_json(url, cacheable=cacheable)[0]

    def _get_json(self, url: str, *, cacheable: bool = False) -> tuple[Any, bool]:
        """`get_json`'s document, and whether the disk cache answered it (True) or the venue did."""
        if cacheable and self.cache is not None:
            body = self.cache.get(url)
            if body is not None:
                try:
                    self.cache_hits += 1
                    return json.loads(body.decode("utf-8")), True
                except (UnicodeDecodeError, ValueError):
                    pass
        delay = 1.0
        last = ""
        for attempt in range(self.max_retries + 1):
            self._check_deadline()
            self._throttle(url)
            self.requests += 1
            try:
                status, headers, body = self.transport.get(url, {"Accept": "application/json"}, 30)
            except Exception as exc:  # a transport failure is retried like a 5xx
                if type(exc).__name__ == "DataError":  # refused locally (size, scheme): final
                    raise HistoryError(f"{url[:160]}: {exc}") from exc
                status, headers, body, last = 0, {}, b"", f"{type(exc).__name__}: {exc}"
            if status:
                self._pace(url, status == 429)
            if status == 429:
                self.rate_limited += 1
            if status == 200:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise HistoryError(f"malformed JSON from {url[:160]}") from exc
                if cacheable and self.cache is not None:
                    self.cache.put(url, body)
                return payload, False
            if status and status != 429 and status < 500:
                snippet = body[:200].decode("utf-8", "replace") if body else ""
                raise HistoryError(f"HTTP {status} from {url[:160]}: {snippet}")
            last = f"HTTP {status}" if status else last
            if attempt < self.max_retries:
                wait = delay
                try:
                    wait = max(wait, min(60.0, float((headers or {}).get("retry-after") or 0))) if status else wait
                except (TypeError, ValueError, AttributeError):
                    pass
                self._check_deadline(wait)
                if attempt >= 2:
                    self.say(f"{last} from {urllib.parse.urlsplit(url).netloc}; retry {attempt + 1} in {wait:.0f}s")
                self.sleep(wait)
                delay = min(delay * 2, 30.0)
        raise HistoryError(f"{url[:160]} failed after {self.max_retries} retries: {last}")

    def _settled_window(self, end_ts: float, margin: float) -> bool:
        return float(end_ts) <= float(self.clock()) - margin

    def say(self, text: str) -> None:
        if self.verbose:
            _log(text)

    # ---------------------------------------------------------------- kalshi
    def kalshi_settled(
        self,
        series: str | None = None,
        *,
        start_ts: float,
        end_ts: float,
        max_pages: int = 20,
        min_volume: float = 0,
    ) -> list[dict[str, Any]]:
        """Settled single markets closing in [start_ts, end_ts], parsed like
        `KalshiMarketData.parse_market` plus `result`, `open_time`, `volume` and
        `settlement_value` (dollars a YES contract paid). Combos (KXMVE) are excluded.

        Only pages fetched from the venue are said (Sept 24, 2026: about 3,200 lines every 30
        minutes in the House's log were reads the disk cache answered, said as if fetched); a read
        the cache answered whole is one line with `debug`, and none without."""
        from .data.kalshi import KalshiMarketData

        cacheable = self._settled_window(end_ts, LISTING_SETTLE_SECONDS)
        out: list[dict[str, Any]] = []
        cursor = None
        pages = fetched = 0
        for _ in range(max(1, int(max_pages))):
            params: dict[str, Any] = {
                "status": "settled",
                "min_close_ts": int(start_ts),
                "max_close_ts": int(end_ts),
                "mve_filter": "exclude",
                "limit": 1000,
            }
            if series:
                params["series_ticker"] = str(series).upper()
            if cursor:
                params["cursor"] = cursor
            payload, cached = self._get_json(f"{KALSHI}/markets?" + urllib.parse.urlencode(params), cacheable=cacheable)
            pages += 1
            fetched += 0 if cached else 1
            rows = payload.get("markets") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise HistoryError("kalshi settled markets: no markets array")
            for row in rows:
                if not isinstance(row, dict) or str(row.get("ticker") or "").startswith("KXMVE"):
                    continue
                try:
                    parsed = KalshiMarketData.parse_market(row)
                except Exception:
                    continue
                volume = _float(row.get("volume_fp") if row.get("volume_fp") is not None else row.get("volume")) or 0.0
                if volume < float(min_volume):
                    continue
                parsed["volume"] = Decimal(str(volume))
                parsed["result"] = str(row.get("result") or "").lower() or None
                parsed["open_time"] = row.get("open_time")
                parsed["settlement_ts"] = row.get("settlement_ts")
                parsed["latest_expiration_time"] = row.get("latest_expiration_time")
                value = row.get("settlement_value_dollars")
                if value is None and row.get("settlement_value") is not None:
                    value = (_float(row.get("settlement_value")) or 0.0) / 100.0
                parsed["settlement_value"] = _float(value)
                out.append(parsed)
            cursor = payload.get("cursor")
            if not cached and fetched % 5 == 0:
                self.say(f"kalshi settled {series or 'board'}: {fetched} pages fetched, {len(out)} markets kept so far")
            if not cursor or not rows:
                break
        else:
            if cursor:
                self.truncated_listings += 1
                self.say(f"kalshi settled {series or 'board'}: stopped at {max_pages} pages; more markets exist")
        if fetched:
            self.say(f"kalshi settled {series or 'board'}: {len(out)} markets in {pages} page(s)"
                     + (f", {pages - fetched} of them from the disk cache" if fetched < pages else ""))
        elif self.debug:
            self.say(f"kalshi settled {series or 'board'}: {len(out)} markets in {pages} page(s), all from the disk cache")
        return out

    @staticmethod
    def parse_candle(row: Any) -> dict[str, Any] | None:
        """One Kalshi candlestick as flat floats (dollars and contracts); None if unusable."""
        if not isinstance(row, dict):
            return None
        try:
            ts = int(row.get("end_period_ts"))
        except (TypeError, ValueError):
            return None
        out: dict[str, Any] = {"ts": ts}
        for side in ("yes_bid", "yes_ask"):
            block = row.get(side) if isinstance(row.get(side), dict) else {}
            for part in ("open", "high", "low", "close"):
                value = block.get(f"{part}_dollars")
                if value is None and block.get(part) is not None:
                    cents = _float(block.get(part))
                    value = None if cents is None else cents / 100.0
                out[f"{side}_{part}"] = _float(value)
        price = row.get("price") if isinstance(row.get("price"), dict) else {}
        for part in ("close", "high", "low"):
            value = price.get(f"{part}_dollars")
            if value is None and price.get(part) is not None:
                cents = _float(price.get(part))
                value = None if cents is None else cents / 100.0
            out[f"price_{part}"] = _float(value)
        volume = row.get("volume_fp") if row.get("volume_fp") is not None else row.get("volume")
        interest = row.get("open_interest_fp") if row.get("open_interest_fp") is not None else row.get("open_interest")
        out["volume"] = _float(volume)
        out["open_interest"] = _float(interest)
        return out

    def kalshi_candles(
        self,
        series: str,
        ticker: str,
        *,
        start_ts: float,
        end_ts: float,
        period_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """One market's candlesticks in [start_ts, end_ts], ascending; `ts` is the period end."""
        period = int(period_minutes) * 60
        cacheable = self._settled_window(end_ts, CANDLE_SETTLE_SECONDS)
        found: dict[int, dict[str, Any]] = {}
        lo = int(start_ts)
        while lo < int(end_ts):
            hi = min(int(end_ts), lo + period * SINGLE_PERIODS)
            params = {"start_ts": lo, "end_ts": hi, "period_interval": int(period_minutes)}
            url = (
                f"{KALSHI}/series/{urllib.parse.quote(str(series).upper())}/markets/"
                f"{urllib.parse.quote(str(ticker).upper())}/candlesticks?" + urllib.parse.urlencode(params)
            )
            payload = self.get_json(url, cacheable=cacheable)
            for row in (payload.get("candlesticks") or []) if isinstance(payload, dict) else []:
                candle = self.parse_candle(row)
                if candle is not None and int(start_ts) <= candle["ts"] <= int(end_ts) + period:
                    found[candle["ts"]] = candle
            lo = hi
        return [found[k] for k in sorted(found)]

    def kalshi_candles_many(
        self,
        tickers: Iterable[str],
        *,
        start_ts: float,
        end_ts: float,
        period_minutes: int = 60,
    ) -> dict[str, list[dict[str, Any]]]:
        """Candlesticks for many markets over one window through the batch endpoint, chunked to
        its limits (100 markets, 10,000 candles counted as markets x periods)."""
        names = sorted({str(t).upper() for t in tickers if t})
        out: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
        if not names:
            return out
        period = int(period_minutes) * 60
        periods = max(1, int(math.ceil((float(end_ts) - float(start_ts)) / period)) + 1)
        if periods > BATCH_CANDLES:
            # Too long a window for even one market in a batch: fall back to the single endpoint.
            for name in names:
                out[name] = self.kalshi_candles(name.split("-")[0], name, start_ts=start_ts, end_ts=end_ts, period_minutes=period_minutes)
            return out
        per_call = max(1, min(BATCH_MARKETS, BATCH_CANDLES // periods))
        cacheable = self._settled_window(end_ts, CANDLE_SETTLE_SECONDS)
        for index in range(0, len(names), per_call):
            chunk = names[index : index + per_call]
            params = {
                "market_tickers": ",".join(chunk),
                "start_ts": int(start_ts),
                "end_ts": int(end_ts),
                "period_interval": int(period_minutes),
            }
            payload = self.get_json(f"{KALSHI}/markets/candlesticks?" + urllib.parse.urlencode(params, safe=","), cacheable=cacheable)
            for market in (payload.get("markets") or []) if isinstance(payload, dict) else []:
                if not isinstance(market, dict):
                    continue
                name = str(market.get("market_ticker") or "").upper()
                if name not in out:
                    continue
                rows = []
                for row in market.get("candlesticks") or []:
                    candle = self.parse_candle(row)
                    if candle is not None:
                        rows.append(candle)
                rows.sort(key=lambda c: c["ts"])
                out[name] = rows
        return out

    # -------------------------------------------------------------- coinbase
    def coinbase_candles(
        self,
        product: str,
        *,
        start_ts: float,
        end_ts: float,
        granularity: str = "FIVE_MINUTE",
    ) -> list[dict[str, Any]]:
        """Candles with start in [start_ts, end_ts], ascending; `ts` is the candle's start."""
        granularity = str(granularity).upper()
        seconds = GRANULARITY_SECONDS.get(granularity)
        if not seconds:
            raise HistoryError(f"coinbase: unsupported granularity {granularity!r}")
        pid = str(product).upper()
        # Chunk on a fixed grid so the same window always asks the same URLs (cache hits).
        first = int(start_ts) // seconds * seconds
        last = int(end_ts)
        found: dict[int, dict[str, Any]] = {}
        chunk = seconds * COINBASE_CHUNK
        lo = first // chunk * chunk
        while lo <= last:
            hi = lo + chunk - seconds
            params = {"start": str(lo), "end": str(hi), "granularity": granularity}
            url = f"{COINBASE}/products/{urllib.parse.quote(pid)}/candles?" + urllib.parse.urlencode(params)
            cacheable = self._settled_window(hi + seconds, CANDLE_SETTLE_SECONDS)
            payload = self.get_json(url, cacheable=cacheable)
            for row in (payload.get("candles") or []) if isinstance(payload, dict) else []:
                if not isinstance(row, dict):
                    continue
                try:
                    ts = int(float(row.get("start")))
                except (TypeError, ValueError):
                    continue
                values = {name: _float(row.get(name)) for name in ("open", "high", "low", "close", "volume")}
                if any(values[name] is None or values[name] <= 0 for name in ("open", "high", "low", "close")):
                    continue
                if int(start_ts) <= ts <= int(end_ts):
                    found[ts] = {"ts": ts, **values}
            lo += chunk
        return [found[k] for k in sorted(found)]


__all__ = ["History", "HistoryError", "HistoryTimeout", "DiskCache", "GRANULARITY_SECONDS", "KALSHI", "COINBASE"]

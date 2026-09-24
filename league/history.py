"""Deep history: a resumable store of Alpaca bars, quotes and trades, and the CLI that fills it.

The replay gate has been judging strategies on 21 days of tape (Sept 22, 2026: replay covered 21
of 126 days, and 6.5% of trials passed), while the owner's plan (Algo Trader Plus: SIP, OPRA, bars
since 2016, 10,000 calls a minute) can supply a decade. This module is the first half of using
it: it fetches history once, keeps it on the House box, and says exactly what it holds.

    python -m league.history ingest --universe core --timeframes 1Day,1Hour [--since 2016-01-01] [--max-minutes N]
                                    [--max-calls N] [--quotes set] [--refresh-adjusted]
    python -m league.history coverage [--json]

**Every call passes through the gateway Worker** (the box holds no Alpaca key). Alpaca pages by
time span, not by `limit` (measured Sept 22, 2026: about 184 hourly or 2,200 five-minute bars a
page), so a decade of hourly bars is about two calls per symbol-month. `--max-calls` bounds a run
so an ingestion can never eat the Worker's request allowance the live House depends on.

**Where.** One SQLite file, `<root>/history/history.sqlite` (on the box `/workspace/state/history/`),
in WAL mode so the House can read it while an ingestion writes. It is private data and never
leaves the box: `.data/` and the state directory are outside every commit.

**Chunks.** Work is cut into (symbol, timeframe, feed, adjustment, day range) chunks: a calendar
year of daily bars, a calendar month of intraday ones, one New York trading day of quote probes.
A chunk is committed with its rows in one transaction, and its completion record is the
`coverage` table, so a killed run loses at most the chunks in flight and the next run starts
where it stopped. States:

    done     the venue returned rows and the range is settled (it ended over a day ago)
    empty    the venue answered 200 with NOTHING for the range: the input is UNAVAILABLE (the
             symbol did not trade yet, crypto before 2021, a holiday) -- not a gap
    open     fetched, but the range reaches into the present, so it is fetched again next run
    failed   the venue refused or did not answer; retried next run
    (absent) never fetched: UNFETCHED, which is a gap in this store, never a fact about markets

**Provenance.** Every chunk records its source (`alpaca`), feed (`sip`, `iex`, or the crypto
location `us`), adjustment, the exact request parameters, the call count and the fetch time.
Every run is a row in `runs`; the House turns each finished run into one `data.coverage` ledger
row (`publish_coverage`), so the ledger says what history existed when a replay was judged.
The ingestion process never writes the ledger itself: only the House opens that file for writing.

**Point in time.** Equity bars are stored twice at the signal timeframes (1Day, 1Hour): `raw`,
the prices that actually printed, and `all`, split- and dividend-adjusted as of the fetch. The
live House shows strategies `all` bars adjusted as of NOW; the honest replay of a moment T shows
bars adjusted as of T, which is `raw(d) * F(d) / F(T)` with `F = all / raw` (the ratio is a step
function of the corporate actions after d, so no corporate-actions feed is needed). Execution
(fills, limit prices, share counts) uses `raw` bars and `raw` quotes; quotes are never adjusted.
5-minute bars are stored `raw` only: they are the execution clock. Crypto has no adjustment.

**Survivorship.** The universes are TODAY's niche lists. Names delisted since 2016 are absent, so
a strategy choosing among these symbols is judged on survivors. Every coverage row says so.

**Rate.** A token bucket shared by the workers holds ingestion to `--rate` calls a minute (1,500
by default, 15% of the plan's 10,000, leaving the live House its room); a 429 backs the whole
bucket off. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .tapes import (
    CRYPTO_BARS_PATH,
    DATA_URL,
    STOCK_BARS_PATH,
    TIMEFRAME_SECONDS,
    TapeError,
    _float,
    _quote_time,
    is_crypto,
    iso,
    parse_time,
)

SOURCE = "alpaca"
HISTORY_DIR = "history"
DB_NAME = "history.sqlite"
DEFAULT_SINCE = "2016-01-01"
NEW_YORK = ZoneInfo("America/New_York")
TRADING_URL = "https://api.alpaca.markets"
CRYPTO_QUOTES_PATH = "/v1beta3/crypto/us/quotes"
CRYPTO_TRADES_PATH = "/v1beta3/crypto/us/trades"
STOCK_QUOTES_PATH = "/v2/stocks/quotes"
STOCK_TRADES_PATH = "/v2/stocks/trades"
CALENDAR_PATH = "/v2/calendar"
#: Listed options (OPRA): bars since Feb 2024 on the owner's plan. Stored like any other symbol,
#: raw, under feed `opra`, so the options replay can be built on this store.
OPTION_BARS_PATH = "/v1beta1/options/bars"
_OCC = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")
PAGE_LIMIT = 10_000
#: A chunk that still has pages after this many is refused rather than followed forever.
MAX_PAGES_PER_CHUNK = 200
#: A range is settled (its chunk can be `done`) once it ended this long ago.
SETTLE_SECONDS = 86400
#: Calls a minute, by default. The plan allows 10,000; the live House needs a few hundred.
DEFAULT_RATE = 1500
DEFAULT_WORKERS = 4
#: The signal timeframes stored in both adjustments; everything else is raw only.
DUAL_ADJUSTED = ("1Day", "1Hour")
#: How far back a quote probe looks for the prevailing quote. Nothing inside it: unavailable.
PROBE_LOOKBACK_SECONDS = 3600
#: The probe asks for the quote prevailing this long after a bar closes: an order decided at the
#: close reaches the venue about then. The replay reads it as the execution clock.
PROBE_LATENCY_SECONDS = 2.0
#: A trade window: the prints in the first minute after a probe time.
TRADE_WINDOW_SECONDS = 60

LIMITATIONS = (
    "survivorship: universes are today's niche lists; names delisted since 2016 are absent",
    "adjustment: `all` bars are adjusted as of the fetch; point-in-time views divide by F(T)",
    "crypto: Alpaca crypto history begins 2021-01-01; earlier ranges are unavailable, not missing",
    "quotes: probes are single NBBO snapshots at bar closes plus latency; no depth, no queue position",
)

# ------------------------------------------------------------------ universes
#: The first instruments fetched: the liquid ones the niches and seeds use most.
TIER_ONE = ("SPY", "QQQ", "IWM", "BTC/USD", "ETH/USD")
#: 5-minute bars (the execution clock of every daily tape) for the most-used symbols.
FIVE_MINUTE_SET = ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLK", "XLF", "XLE", "XLV", "SMH", "EEM",
                   "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD",
                   "BTC/USD", "ETH/USD", "SOL/USD")
#: Quote probes and trade windows, for execution modeling: a small liquid set.
QUOTE_SET = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "BTC/USD", "ETH/USD")


def niche_symbols(asset_classes: Iterable[str] = ("equity", "crypto", "option")) -> list[str]:
    """Every Alpaca symbol the niches list, in file order (options niches list underliers)."""
    from .niches import NICHES_PATH

    wanted = set(asset_classes)
    out: list[str] = []
    for niche in json.loads(NICHES_PATH.read_text(encoding="utf-8")).get("niches", []):
        if niche.get("venue") != "alpaca" or niche.get("asset_class") not in wanted:
            continue
        for symbol in niche.get("symbols") or ():
            if symbol not in out:
                out.append(str(symbol).upper())
    return out


def universe(name: str) -> list[str]:
    """`core`: the index ETFs, the megacaps and the crypto majors. `all`: every niche symbol."""
    if name == "core":
        core = niche_symbols(("equity",)) + ["BTC/USD", "ETH/USD", "SOL/USD"]
    elif name == "all":
        core = niche_symbols()
    elif name == "tier1":
        core = list(TIER_ONE)
    else:
        raise ValueError(f"unknown universe {name!r}: core, all or tier1")
    first = [s for s in TIER_ONE if s in core]
    return first + [s for s in core if s not in first]


# ------------------------------------------------------------------- helpers

def _day(value: "str | date") -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _ts(day: date) -> float:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()


def _ns(stamp: Any) -> "int | None":
    """An RFC 3339 time with nanoseconds as integer nanoseconds since the epoch (exact)."""
    text = _quote_time(stamp)
    if text is None:
        return None
    raw = str(stamp).strip()
    frac = ""
    if "." in raw:
        frac = raw.split(".", 1)[1].rstrip("Zz")
        for sign in ("+", "-"):
            frac = frac.split(sign, 1)[0]
    whole = int(parse_time(text[:19] + "Z"))
    return whole * 1_000_000_000 + int((frac + "000000000")[:9] or 0)


def chunk_ranges(timeframe: str, since: date, until: date) -> list[tuple[date, date]]:
    """The chunk ranges [start, end) covering [since, until): years for 1Day, months otherwise."""
    out: list[tuple[date, date]] = []
    if timeframe == "1Day":
        year = since.year
        while date(year, 1, 1) < until:
            start, end = max(date(year, 1, 1), since), min(date(year + 1, 1, 1), until)
            if start < end:
                out.append((start, end))
            year += 1
        return out
    cursor = date(since.year, since.month, 1)
    while cursor < until:
        nxt = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        start, end = max(cursor, since), min(nxt, until)
        if start < end:
            out.append((start, end))
        cursor = nxt
    return out


def is_option(symbol: str) -> bool:
    """An OCC option symbol: root, expiry YYMMDD, C or P, strike x 1000 in eight digits."""
    return bool(_OCC.match(str(symbol)))


def asset_class(symbol: str) -> str:
    return "crypto" if is_crypto(symbol) else "option" if is_option(symbol) else "equity"


FEEDS = {"crypto": "us", "option": "opra"}


def group_size(timeframe: str, crypto: bool, option: bool = False) -> int:
    """Symbols per request, so one chunk is about one 10,000-bar page."""
    if option:
        return 20  # an option trades sparsely: most minutes of most contracts have no bar
    if timeframe == "1Day":
        return 12
    if timeframe == "1Hour":
        return 6
    return 1 if crypto else 2


class RateLimiter:
    """A token bucket shared by every worker: `rate` calls a minute, bursts of a second's worth."""

    def __init__(self, rate_per_minute: float, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rate = max(1.0, float(rate_per_minute)) / 60.0
        self.capacity = max(1.0, self.rate)
        self.tokens = self.capacity
        self.clock, self.sleep = clock, sleep
        self.stamp = clock()
        self.paused_until = 0.0
        self.calls = 0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self.clock()
                self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.rate)
                self.stamp = now
                wait_for = max(0.0, self.paused_until - now)
                if not wait_for and self.tokens >= 1.0 - 1e-9:
                    self.tokens = max(0.0, self.tokens - 1.0)
                    self.calls += 1
                    return
                wait_for = wait_for or (1.0 - self.tokens) / self.rate
            self.sleep(min(max(wait_for, 0.001), 5.0))

    def back_off(self, seconds: float) -> None:
        with self._lock:
            self.paused_until = max(self.paused_until, self.clock() + float(seconds))


# --------------------------------------------------------------------- store

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, feed TEXT NOT NULL, adjustment TEXT NOT NULL,
    t INTEGER NOT NULL,           -- the bar's OPEN, epoch seconds, as Alpaca stamps it
    o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL,
    n INTEGER, vw REAL,
    PRIMARY KEY (symbol, timeframe, feed, adjustment, t)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS probes (
    symbol TEXT NOT NULL, feed TEXT NOT NULL,
    t INTEGER NOT NULL,           -- the bar close the probe belongs to, epoch seconds
    at REAL NOT NULL,             -- the moment asked about: t + latency
    quote_ns INTEGER,             -- when the prevailing quote was set; NULL: none in the lookback
    bp REAL, bs REAL, ap REAL, "as" REAL, bx TEXT, ax TEXT, c TEXT,
    PRIMARY KEY (symbol, feed, t)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS trades (
    symbol TEXT NOT NULL, feed TEXT NOT NULL, t_ns INTEGER NOT NULL, i TEXT NOT NULL, x TEXT NOT NULL,
    p REAL NOT NULL, s REAL NOT NULL, c TEXT,
    PRIMARY KEY (symbol, feed, t_ns, i, x)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sessions (
    day TEXT PRIMARY KEY, open_ts INTEGER NOT NULL, close_ts INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS coverage (
    kind TEXT NOT NULL,           -- bars | probes | trades | sessions
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, feed TEXT NOT NULL, adjustment TEXT NOT NULL,
    start TEXT NOT NULL, "end" TEXT NOT NULL,   -- days, end exclusive
    state TEXT NOT NULL,          -- done | empty | open | failed
    rows INTEGER NOT NULL DEFAULT 0, first_t INTEGER, last_t INTEGER,
    source TEXT NOT NULL, params TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
    fetched_at REAL NOT NULL, run TEXT, error TEXT,
    PRIMARY KEY (kind, symbol, timeframe, feed, adjustment, start, "end")
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS runs (
    run TEXT PRIMARY KEY, pid INTEGER, started_at REAL NOT NULL, finished_at REAL,
    status TEXT NOT NULL,         -- running | finished | stopped | interrupted | failed
    args TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, rows INTEGER NOT NULL DEFAULT 0,
    chunks TEXT NOT NULL DEFAULT '{}', error TEXT
);
"""

COVERAGE_STATES = ("done", "empty", "open", "failed")


@dataclass(frozen=True)
class Chunk:
    kind: str
    symbols: tuple[str, ...]
    timeframe: str
    feed: str
    adjustment: str
    start: date
    end: date

    def label(self) -> str:
        return f"{self.kind} {','.join(self.symbols)} {self.timeframe} {self.adjustment} {self.start}..{self.end}"


class HistoryStore:
    """The SQLite file. One writer (the ingestion), any number of readers (the House)."""

    def __init__(self, path: "str | Path", *, clock: Callable[[], float] = time.time, readonly: bool = False):
        self.path = Path(path)
        self.clock = clock
        self._lock = threading.RLock()
        if readonly:
            self._db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False, timeout=30)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=60)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)
            os.chmod(self.path, 0o600)
        self._db.row_factory = sqlite3.Row

    @classmethod
    def at_root(cls, root: "str | Path", **kwargs: Any) -> "HistoryStore":
        return cls(Path(root) / HISTORY_DIR / DB_NAME, **kwargs)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _rows(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # ------------------------------------------------------------- writes
    def commit_chunk(self, chunk: Chunk, symbol: str, *, state: str, rows: Sequence[tuple] = (), table: str = "bars",
                     first_t: "int | None" = None, last_t: "int | None" = None, params: Mapping[str, Any] | None = None,
                     calls: int = 0, run: "str | None" = None, error: "str | None" = None) -> None:
        """One chunk's rows and its completion record, in one transaction."""
        if state not in COVERAGE_STATES:
            raise ValueError(f"unknown chunk state {state!r}")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if rows and table == "bars":
                    self._db.executemany(
                        "INSERT OR REPLACE INTO bars (symbol, timeframe, feed, adjustment, t, o, h, l, c, v, n, vw)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(symbol, chunk.timeframe, chunk.feed, chunk.adjustment, *row) for row in rows])
                elif rows and table == "probes":
                    self._db.executemany(
                        'INSERT OR REPLACE INTO probes (symbol, feed, t, at, quote_ns, bp, bs, ap, "as", bx, ax, c)'
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(symbol, chunk.feed, *row) for row in rows])
                elif rows and table == "trades":
                    self._db.executemany(
                        "INSERT OR REPLACE INTO trades (symbol, feed, t_ns, i, x, p, s, c) VALUES (?,?,?,?,?,?,?,?)",
                        [(symbol, chunk.feed, *row) for row in rows])
                if state == "failed":
                    # A failure never overwrites what an earlier run completed.
                    prior = self._db.execute(
                        'SELECT state FROM coverage WHERE kind=? AND symbol=? AND timeframe=? AND feed=? AND adjustment=? AND start=? AND "end"=?',
                        (chunk.kind, symbol, chunk.timeframe, chunk.feed, chunk.adjustment, str(chunk.start), str(chunk.end))).fetchone()
                    if prior is not None and prior["state"] in ("done", "empty", "open"):
                        self._db.execute("COMMIT")
                        return
                self._db.execute(
                    'INSERT OR REPLACE INTO coverage (kind, symbol, timeframe, feed, adjustment, start, "end", state, rows,'
                    " first_t, last_t, source, params, calls, fetched_at, run, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (chunk.kind, symbol, chunk.timeframe, chunk.feed, chunk.adjustment, str(chunk.start), str(chunk.end),
                     state, len(rows), first_t, last_t, SOURCE, json.dumps(dict(params or {}), sort_keys=True), int(calls),
                     float(self.clock()), run, (error or None) and str(error)[:300]))
                self._db.execute("COMMIT")
            except BaseException:
                try:
                    self._db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    def put_sessions(self, sessions: Iterable[tuple[str, int, int]]) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.executemany("INSERT OR REPLACE INTO sessions (day, open_ts, close_ts) VALUES (?,?,?)", list(sessions))
            self._db.execute("COMMIT")

    def begin_run(self, args: Mapping[str, Any]) -> str:
        run = datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        with self._lock:
            # A run still marked running whose process is gone was killed: say so, once.
            for row in self._db.execute("SELECT run, pid FROM runs WHERE status='running'").fetchall():
                if not _alive(row["pid"]):
                    self._db.execute("UPDATE runs SET status='interrupted', finished_at=? WHERE run=?", (self.clock(), row["run"]))
            self._db.execute("INSERT INTO runs (run, pid, started_at, status, args) VALUES (?,?,?,?,?)",
                             (run, os.getpid(), self.clock(), "running", json.dumps(dict(args), sort_keys=True, default=str)))
        return run

    def progress_run(self, run: str, *, calls: int, rows: int, chunks: Mapping[str, int]) -> None:
        with self._lock:
            self._db.execute("UPDATE runs SET calls=?, rows=?, chunks=? WHERE run=?",
                             (int(calls), int(rows), json.dumps(dict(chunks), sort_keys=True), run))

    def finish_run(self, run: str, status: str, *, error: "str | None" = None) -> None:
        with self._lock:
            self._db.execute("UPDATE runs SET status=?, finished_at=?, error=? WHERE run=?",
                             (status, self.clock(), (error or None) and str(error)[:500], run))

    # -------------------------------------------------------------- reads
    def chunk_state(self, kind: str, symbol: str, timeframe: str, feed: str, adjustment: str, start: date, end: date) -> "str | None":
        row = self._rows('SELECT state FROM coverage WHERE kind=? AND symbol=? AND timeframe=? AND feed=? AND adjustment=?'
                         ' AND start=? AND "end"=?', (kind, symbol, timeframe, feed, adjustment, str(start), str(end)))
        return row[0]["state"] if row else None

    def fetched_at(self, chunk: Chunk, symbol: str) -> "float | None":
        row = self._rows('SELECT fetched_at FROM coverage WHERE kind=? AND symbol=? AND timeframe=? AND feed=? AND adjustment=?'
                         ' AND start=? AND "end"=?', (chunk.kind, symbol, chunk.timeframe, chunk.feed, chunk.adjustment,
                                                     str(chunk.start), str(chunk.end)))
        return row[0]["fetched_at"] if row else None

    def chunk_rows(self, kind: "str | None" = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM coverage", []
        if kind:
            sql, params = sql + " WHERE kind=?", [kind]
        return [dict(row) for row in self._rows(sql + " ORDER BY kind, symbol, timeframe, adjustment, start", params)]

    def runs(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows("SELECT * FROM runs ORDER BY started_at")]

    def bars(self, symbol: str, timeframe: str, start_ts: float, end_ts: float, *, feed: str, adjustment: str) -> list[dict[str, Any]]:
        """Stored bars whose OPEN is in [start_ts, end_ts), oldest first, in Alpaca's own shape."""
        rows = self._rows("SELECT t, o, h, l, c, v, n, vw FROM bars WHERE symbol=? AND timeframe=? AND feed=? AND adjustment=?"
                          " AND t >= ? AND t < ? ORDER BY t", (symbol, timeframe, feed, adjustment, int(start_ts), int(end_ts)))
        return [dict(row) for row in rows]

    def probes(self, symbol: str, start_ts: float, end_ts: float, *, feed: str) -> list[dict[str, Any]]:
        rows = self._rows('SELECT t, at, quote_ns, bp, bs, ap, "as", bx, ax, c FROM probes WHERE symbol=? AND feed=?'
                          " AND t >= ? AND t < ? ORDER BY t", (symbol, feed, int(start_ts), int(end_ts)))
        return [dict(row) for row in rows]

    def sessions(self, start: date, end: date) -> list[tuple[str, int, int]]:
        return [(r["day"], r["open_ts"], r["close_ts"]) for r in
                self._rows("SELECT day, open_ts, close_ts FROM sessions WHERE day >= ? AND day < ? ORDER BY day", (str(start), str(end)))]

    def first_bar(self, symbol: str, timeframe: str, *, feed: str, adjustment: str) -> "int | None":
        row = self._rows("SELECT MIN(t) AS t FROM bars WHERE symbol=? AND timeframe=? AND feed=? AND adjustment=?",
                         (symbol, timeframe, feed, adjustment))
        return row[0]["t"] if row and row[0]["t"] is not None else None

    def coverage(self, symbol: str, timeframe: str, start: "str | date", end: "str | date", *, feed: str,
                 adjustment: str = "raw", kind: str = "bars") -> dict[str, Any]:
        """What this store can say about [start, end) for one series.

        `status` is `covered` (every chunk fetched, rows present), `unavailable` (every chunk
        fetched and the venue had nothing), `partial` (fetched, but some of it unavailable: the
        symbol listed inside the window), `unfetched` (some chunk never fetched or failed: a gap
        in THIS STORE, which must never be read as a negative result). `available_from` is the
        first stored bar when the window starts before the symbol traded."""
        lo, hi = _day(start), _day(end)
        states: dict[str, list[list[str]]] = {"done": [], "empty": [], "open": [], "failed": [], "unfetched": []}
        if kind == "probes":
            ranges = [(lo + timedelta(days=i), lo + timedelta(days=i + 1)) for i in range((hi - lo).days)]
        else:
            ranges = chunk_ranges(timeframe, lo, hi)
        recorded = {(r["start"], r["end"]): r for r in self._rows(
            'SELECT start, "end", state, fetched_at FROM coverage WHERE kind=? AND symbol=? AND timeframe=? AND feed=? AND adjustment=?'
            ' AND "end" > ? AND start < ?', (kind, symbol, timeframe, feed, adjustment, str(lo), str(hi)))}
        for a, b in ranges:
            row = _find_chunk(recorded, a, b)
            state = row["state"] if row else "unfetched"
            states["unfetched" if state == "failed" else state].append([str(a), str(b)])
            if state == "failed":
                states["failed"].append([str(a), str(b)])
        fetched = not states["unfetched"]
        has_rows = bool(states["done"] or states["open"])
        status = ("unfetched" if not fetched else "unavailable" if not has_rows
                  else "partial" if states["empty"] else "covered")
        table = "probes" if kind == "probes" else "bars"
        if table == "bars":
            count = self._rows("SELECT COUNT(*) AS n, MIN(t) AS lo, MAX(t) AS hi FROM bars WHERE symbol=? AND timeframe=? AND feed=?"
                               " AND adjustment=? AND t >= ? AND t < ?", (symbol, timeframe, feed, adjustment, int(_ts(lo)), int(_ts(hi))))[0]
        else:
            count = self._rows("SELECT COUNT(quote_ns) AS n, MIN(t) AS lo, MAX(t) AS hi FROM probes WHERE symbol=? AND feed=?"
                               " AND t >= ? AND t < ?", (symbol, feed, int(_ts(lo)), int(_ts(hi))))[0]
        return {"symbol": symbol, "timeframe": timeframe, "feed": feed, "adjustment": adjustment, "kind": kind,
                "start": str(lo), "end": str(hi), "status": status, "rows": int(count["n"] or 0),
                "first": iso(count["lo"]) if count["lo"] is not None else None,
                "last": iso(count["hi"]) if count["hi"] is not None else None,
                "available_from": iso(count["lo"]) if status == "partial" and count["lo"] is not None else None,
                "unfetched": states["unfetched"], "failed": states["failed"], "unavailable": states["empty"],
                "open": states["open"]}

    def summary(self) -> list[dict[str, Any]]:
        """Per series: chunk counts by state, stored rows, first and last bar, last fetch."""
        out = []
        for row in self._rows(
                "SELECT kind, symbol, timeframe, feed, adjustment, COUNT(*) AS chunks,"
                " SUM(state='done') AS done, SUM(state='empty') AS empty, SUM(state='open') AS open, SUM(state='failed') AS failed,"
                " SUM(rows) AS rows, SUM(calls) AS calls, MIN(CASE WHEN state IN ('done','open') THEN start END) AS first_day,"
                " MAX(CASE WHEN state IN ('done','open') THEN \"end\" END) AS last_day, MAX(fetched_at) AS fetched_at"
                " FROM coverage GROUP BY kind, symbol, timeframe, feed, adjustment ORDER BY kind, timeframe, symbol, adjustment"):
            item = dict(row)
            item["fetched_at"] = iso(item["fetched_at"]) if item["fetched_at"] else None
            out.append(item)
        return out


def series_without_bars(store: HistoryStore, symbols: Sequence[str], timeframe: str, start: "str | date", end: "str | date",
                        *, feed: str = "sip") -> list[str]:
    """Why a tape of these symbols over [start, end) could not be replayed: one line for each
    symbol whose stored bars a tape's steps are cut from (the execution series: 5-minute bars under
    a daily signal, else the signal timeframe; crypto raw on `us`, an equity adjusted at 1Day and
    1Hour and raw below) hold no bar in the window although the window was fetched. Empty when every
    symbol has one. A range never fetched is a gap in THIS store and is left to `coverage_gaps`
    (league/deep_replay.py), which falls back to the live tape; this is the other case, where the
    venue answered and had nothing: the symbol did not trade yet.

    Sept 24, 2026 (D1's root): the store held ADA/USD 15-minute bars only from 2026-02-01, and a
    development tape of ADA/USD over 2025-09-12..2025-11-14 was built with no steps; the lab's step
    then failed on it every minute for over two hours."""
    execution = "5Min" if timeframe == "1Day" else timeframe
    out = []
    for symbol in symbols:
        crypto = asset_class(symbol) == "crypto"
        series_feed = "us" if crypto else feed
        adjustment = "raw" if crypto or execution not in DUAL_ADJUSTED else "all"
        cover = store.coverage(symbol, execution, start, end, feed=series_feed, adjustment=adjustment)
        if cover["status"] == "unfetched" or cover["rows"]:
            continue
        first = store.first_bar(symbol, execution, feed=series_feed, adjustment=adjustment)
        since = f"its first is {iso(first)[:10]}" if first is not None else "it holds none at all"
        out.append(f"the history store holds no {symbol} {execution} bars in {cover['start']}..{cover['end']} ({since}): "
                   "nothing was recorded in this window, so nothing can be replayed on it")
    return out


def _find_chunk(recorded: Mapping[tuple[str, str], Any], a: date, b: date) -> Any:
    """The record covering [a, b): the exact chunk, or the chunk grid's one that contains it."""
    row = recorded.get((str(a), str(b)))
    if row is not None:
        return row
    for (start, end), candidate in recorded.items():
        if start <= str(a) and str(b) <= end:
            return candidate
    return None


def _alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


# ----------------------------------------------------------------- ingestion

class VenueFailure(RuntimeError):
    """The venue refused or did not answer after the retries."""


class BudgetSpent(RuntimeError):
    """The run's call budget is spent: the chunk in hand is left unfetched, not failed."""


@dataclass
class Tally:
    calls: int = 0
    rows: int = 0
    chunks: dict[str, int] = field(default_factory=lambda: {"done": 0, "empty": 0, "open": 0, "failed": 0, "skipped": 0})


class Ingestor:
    """Fetches chunks through the gateway (`client.request`, as `AlpacaData` does) into the store."""

    def __init__(self, store: HistoryStore, client: Any, *, feed: str = "sip", rate_per_minute: float = DEFAULT_RATE,
                 workers: int = DEFAULT_WORKERS, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep, retries: int = 4, log: Callable[[str], None] | None = None,
                 refresh_adjusted_before: "float | None" = None):
        self.store, self.client, self.feed = store, client, str(feed)
        #: `all` chunks fetched before this moment are fetched again (see `pending`).
        self.refresh_adjusted_before = refresh_adjusted_before
        self.limiter = RateLimiter(rate_per_minute, sleep=sleep)
        self.workers = max(1, int(workers))
        self.clock, self.sleep, self.retries = clock, sleep, max(0, int(retries))
        self.log = log or (lambda text: None)
        self.tally = Tally()
        self._tally_lock = threading.Lock()
        self.max_calls: "int | None" = None

    # -------------------------------------------------------------- http
    def _get(self, base: str, path: str, params: Mapping[str, Any]) -> Any:
        pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
        url = f"{base}{path}?" + urllib.parse.urlencode(pairs, safe="/,:")
        delay = 2.0
        for attempt in range(self.retries + 1):
            with self._tally_lock:
                if self.max_calls is not None and self.tally.calls >= self.max_calls:
                    raise BudgetSpent(f"{self.max_calls} calls spent")
                self.tally.calls += 1
            self.limiter.acquire()
            try:
                status, payload = self.client.request("GET", url, headers={}, what="alpaca history")
            except Exception as exc:  # noqa: BLE001 - a transport failure: retried, then a chunk failure
                status, payload = None, {"message": f"{type(exc).__name__}: {exc}"}
            if status == 200:
                return payload
            if status == 429:
                self.limiter.back_off(max(delay, 5.0))
            if status is not None and status not in (429,) and 400 <= status < 500:
                break  # a refusal, not a hiccup: retrying cannot help
            if attempt < self.retries:
                self.sleep(delay)
                delay = min(delay * 2, 60.0)
        detail = payload.get("message") if isinstance(payload, dict) else str(payload)[:200]
        raise VenueFailure(f"HTTP {status}: {str(detail or '')[:200]}")

    def _paged(self, base: str, path: str, params: Mapping[str, Any], key: str) -> tuple[dict[str, list[Any]], int]:
        """Every page of one multi-symbol read, by symbol, and how many calls it took."""
        out: dict[str, list[Any]] = {}
        token, calls = None, 0
        for _ in range(MAX_PAGES_PER_CHUNK):
            query = dict(params)
            if token:
                query["page_token"] = token
            payload = self._get(base, path, query)
            calls += 1
            if not isinstance(payload, dict):
                raise VenueFailure("the response is not an object")
            section = payload.get(key)
            if isinstance(section, list):  # the single-symbol shape
                section = {str(payload.get("symbol") or params.get("symbols") or "").upper(): section}
            for symbol, rows in (section or {}).items():
                if isinstance(rows, list):
                    out.setdefault(str(symbol).upper(), []).extend(rows)
            token = payload.get("next_page_token")
            if not token:
                return out, calls
        raise VenueFailure(f"more than {MAX_PAGES_PER_CHUNK} pages in one chunk")

    # -------------------------------------------------------------- plan
    def plan(self, symbols: Sequence[str], timeframes: Sequence[str], since: "str | date", until: "str | date | None" = None,
             *, five_minute: Sequence[str] = FIVE_MINUTE_SET) -> list[Chunk]:
        """Every bar chunk to fetch, daily first (it tells the intraday passes when a symbol began),
        newest range first within a timeframe, so a partial run leaves the recent years complete."""
        lo = _day(since)
        hi = _day(until) if until else (datetime.fromtimestamp(self.clock(), timezone.utc).date() + timedelta(days=1))
        order = {"1Day": 0, "1Hour": 1, "15Min": 2, "5Min": 3, "1Min": 4}
        chunks: list[Chunk] = []
        for timeframe in sorted(dict.fromkeys(timeframes), key=lambda tf: order.get(tf, 9)):
            if timeframe not in TIMEFRAME_SECONDS:
                raise ValueError(f"timeframe must be one of {sorted(TIMEFRAME_SECONDS)}, got {timeframe!r}")
            names = [s for s in symbols if timeframe != "5Min" or s in five_minute or len(symbols) <= 6]
            for start, end in reversed(chunk_ranges(timeframe, lo, hi)):
                for kind in ("equity", "crypto", "option"):
                    group = [s for s in names if asset_class(s) == kind]
                    adjustments = ("raw", "all") if kind == "equity" and timeframe in DUAL_ADJUSTED else ("raw",)
                    size = group_size(timeframe, kind == "crypto", kind == "option")
                    for adjustment in adjustments:
                        for i in range(0, len(group), size):
                            chunks.append(Chunk("bars", tuple(group[i:i + size]), timeframe,
                                                FEEDS.get(kind, self.feed), adjustment, start, end))
        return chunks

    def pending(self, chunk: Chunk) -> list[str]:
        """The symbols of a chunk still to fetch: never fetched, failed, or open (unsettled).

        An `all` chunk is adjusted as of its fetch, so after a split or dividend the chunks fetched
        before it are stale by that event's factor while a later fetch is not. A deep tape must be
        built from one consistent fetch; `--refresh-adjusted` re-fetches every `all` chunk fetched
        before the run began (cheap: daily and hourly only)."""
        out = []
        for symbol in chunk.symbols:
            state = self.store.chunk_state(chunk.kind, symbol, chunk.timeframe, chunk.feed, chunk.adjustment, chunk.start, chunk.end)
            if state in (None, "failed", "open"):
                out.append(symbol)
            elif (self.refresh_adjusted_before is not None and chunk.adjustment == "all"
                  and (self.store.fetched_at(chunk, symbol) or 0) < self.refresh_adjusted_before):
                out.append(symbol)
        return out

    def _before_listing(self, symbol: str, chunk: Chunk) -> bool:
        """An intraday chunk wholly before the symbol's first daily bar, when the daily pass has
        fetched everything from the chunk's start up to that bar: the venue has nothing there."""
        if chunk.timeframe == "1Day" or chunk.kind != "bars":
            return False
        feed = FEEDS.get(asset_class(symbol), self.feed)
        first = self.store.first_bar(symbol, "1Day", feed=feed, adjustment="raw")
        if first is None or _ts(chunk.end) > first:
            return False
        cover = self.store.coverage(symbol, "1Day", chunk.start, datetime.fromtimestamp(first, timezone.utc).date(), feed=feed)
        return not cover["unfetched"]

    # --------------------------------------------------------------- run
    def fetch_bars(self, chunk: Chunk, symbols: Sequence[str], run: "str | None" = None) -> dict[str, str]:
        """Fetch one bar chunk for these symbols and commit each symbol's part. Returns states."""
        kind = asset_class(symbols[0])
        start_ts, end_ts = _ts(chunk.start), _ts(chunk.end)
        params: dict[str, Any] = {"symbols": ",".join(symbols), "timeframe": chunk.timeframe,
                                  "start": iso(start_ts), "end": iso(end_ts - 1), "limit": PAGE_LIMIT}
        if kind == "equity":
            params.update(feed=chunk.feed, adjustment=chunk.adjustment)
        path = {"crypto": CRYPTO_BARS_PATH, "option": OPTION_BARS_PATH}.get(kind, STOCK_BARS_PATH)
        states: dict[str, str] = {}
        inferred = [s for s in symbols if self._before_listing(s, chunk)]
        for symbol in inferred:
            self.store.commit_chunk(chunk, symbol, state="empty", run=run,
                                    params={"inferred": "before the first daily bar", "timeframe": chunk.timeframe})
            states[symbol] = "empty"
        wanted = [s for s in symbols if s not in inferred]
        if not wanted:
            return states
        params["symbols"] = ",".join(wanted)
        try:
            found, calls = self._paged(DATA_URL, path, params, "bars")
        except BudgetSpent:
            return {**states, **{symbol: "skipped" for symbol in wanted}}
        except VenueFailure as exc:
            for symbol in wanted:
                self.store.commit_chunk(chunk, symbol, state="failed", params=params, run=run, error=str(exc))
                states[symbol] = "failed"
            return states
        settled = end_ts <= self.clock() - SETTLE_SECONDS
        for index, symbol in enumerate(wanted):
            rows = []
            for row in found.get(symbol, []):
                parsed = _bar_row(row)
                if parsed is not None and start_ts <= parsed[0] < end_ts:
                    rows.append(parsed)
            rows.sort()
            state = ("done" if rows else "empty") if settled else "open"
            self.store.commit_chunk(chunk, symbol, state=state, rows=rows, params={**params, "symbols": ",".join(wanted)},
                                    calls=calls if index == 0 else 0, run=run,
                                    first_t=rows[0][0] if rows else None, last_t=rows[-1][0] if rows else None)
            states[symbol] = state
            with self._tally_lock:
                self.tally.rows += len(rows)
        return states

    def run(self, chunks: Sequence[Chunk], *, run: "str | None" = None, max_minutes: "float | None" = None,
            stop: "threading.Event | None" = None, max_calls: "int | None" = None) -> Tally:
        """Fetch every pending chunk, `workers` at a time; stop at the time limit, or once
        `max_calls` calls are spent (a chunk cut short by the budget is left unfetched)."""
        deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
        self.max_calls = max_calls
        spent = lambda: max_calls is not None and self.tally.calls >= max_calls  # noqa: E731
        stop = stop or threading.Event()
        work = iter(chunks)
        in_flight: dict[Any, Chunk] = {}

        def submit(pool: ThreadPoolExecutor) -> bool:
            for chunk in work:
                symbols = self.pending(chunk)
                if not symbols:
                    with self._tally_lock:
                        self.tally.chunks["skipped"] += len(chunk.symbols)
                    continue
                fn = {"bars": self.fetch_bars, "probes": self.fetch_probes, "trades": self.fetch_trades}[chunk.kind]
                in_flight[pool.submit(fn, chunk, symbols, run)] = chunk
                return True
            return False

        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="history") as pool:
            exhausted = False
            while True:
                while (not exhausted and len(in_flight) < self.workers and not stop.is_set()
                       and not (deadline and time.monotonic() > deadline) and not spent()):
                    exhausted = not submit(pool)
                if not in_flight:
                    break
                done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    chunk = in_flight.pop(future)
                    try:
                        states = future.result()
                    except Exception as exc:  # noqa: BLE001 - a store failure: record and go on
                        self.log(f"chunk failed: {chunk.label()}: {type(exc).__name__}: {exc}")
                        states = {s: "failed" for s in chunk.symbols}
                    with self._tally_lock:
                        for state in states.values():
                            self.tally.chunks[state] = self.tally.chunks.get(state, 0) + 1
                    if run:
                        self.store.progress_run(run, calls=self.tally.calls, rows=self.tally.rows, chunks=self.tally.chunks)
                    self.log(f"{chunk.label()}: {states}")
        return self.tally

    # ------------------------------------------------------------ quotes
    def sessions(self, since: date, until: date) -> list[tuple[str, int, int]]:
        """The regular sessions in [since, until): the venue's calendar (early closes included)."""
        stored = self.store.sessions(since, until)
        have = {day for day, _, _ in stored}
        chunk = Chunk("sessions", ("*",), "1Day", "calendar", "raw", since, until)
        if self.store.chunk_state("sessions", "*", "1Day", "calendar", "raw", since, until) in ("done",):
            return stored
        payload = self._get(TRADING_URL, CALENDAR_PATH, {"start": str(since), "end": str(until - timedelta(days=1))})
        rows = []
        for entry in payload if isinstance(payload, list) else []:
            try:
                day = str(entry["date"])
                opened = datetime.fromisoformat(f"{day}T{entry['open']}:00").replace(tzinfo=NEW_YORK)
                closed = datetime.fromisoformat(f"{day}T{entry['close']}:00").replace(tzinfo=NEW_YORK)
            except (KeyError, ValueError, TypeError):
                continue
            if day not in have:
                rows.append((day, int(opened.timestamp()), int(closed.timestamp())))
        self.store.put_sessions(rows)
        settled = _ts(until) <= self.clock() - SETTLE_SECONDS
        self.store.commit_chunk(chunk, "*", state="done" if settled else "open", params={"start": str(since), "end": str(until)}, calls=1)
        return self.store.sessions(since, until)

    def probe_plan(self, symbols: Sequence[str], since: "str | date", until: "str | date | None" = None, *,
                   grid: str = "5Min", crypto_grid: str = "15Min") -> list[Chunk]:
        """One chunk per symbol per day, newest day first."""
        lo = _day(since)
        hi = _day(until) if until else datetime.fromtimestamp(self.clock(), timezone.utc).date()
        days = [lo + timedelta(days=i) for i in range((hi - lo).days)]
        out = []
        for day in reversed(days):
            for symbol in symbols:
                crypto = is_crypto(symbol)
                out.append(Chunk("probes", (symbol,), crypto_grid if crypto else grid, "us" if crypto else self.feed,
                                 "raw", day, day + timedelta(days=1)))
        return out

    def probe_times(self, chunk: Chunk, symbol: str) -> list[int]:
        """The bar closes a day's probes ask about: every clock-aligned grid close inside the
        regular session for an equity (none on a closed day), every one of the UTC day for crypto."""
        step = TIMEFRAME_SECONDS[chunk.timeframe]
        if is_crypto(symbol):
            start = int(_ts(chunk.start))
            return [start + step * (i + 1) for i in range(86400 // step)]
        sessions = self.sessions(date(chunk.start.year, chunk.start.month, 1),
                                 date(chunk.start.year + (chunk.start.month == 12), chunk.start.month % 12 + 1, 1))
        for day, open_ts, close_ts in sessions:
            if day == str(chunk.start):
                # Bar closes are clock-aligned (an hourly bar closes at 10:00, not 10:30), so the
                # grid is every multiple of the step after the open, up to and including the close.
                return list(range((open_ts // step + 1) * step, close_ts + 1, step))
        return []

    def fetch_probes(self, chunk: Chunk, symbols: Sequence[str], run: "str | None" = None) -> dict[str, str]:
        """The prevailing quote at each probe time (the last one at or before it, `sort=desc`)."""
        states = {}
        for symbol in symbols:
            crypto = is_crypto(symbol)
            try:
                times = self.probe_times(chunk, symbol)
            except BudgetSpent:
                states[symbol] = "skipped"
                continue
            except VenueFailure as exc:
                self.store.commit_chunk(chunk, symbol, state="failed", run=run, error=f"calendar: {exc}", params={})
                states[symbol] = "failed"
                continue
            rows, calls, error = [], 0, None
            for t in times:
                at = t + PROBE_LATENCY_SECONDS
                if at > self.clock():
                    break
                params: dict[str, Any] = {"symbols": symbol, "start": iso(at - PROBE_LOOKBACK_SECONDS),
                                          "end": _iso_frac(at), "limit": 1, "sort": "desc"}
                if not crypto:
                    params["feed"] = chunk.feed
                try:
                    payload = self._get(DATA_URL, CRYPTO_QUOTES_PATH if crypto else STOCK_QUOTES_PATH, params)
                except BudgetSpent:
                    error = "budget"
                    break
                except VenueFailure as exc:
                    error = str(exc)
                    break
                calls += 1
                section = (payload or {}).get("quotes") if isinstance(payload, dict) else None
                quote = ((section or {}).get(symbol) or [None])[0] if isinstance(section, dict) else None
                rows.append(_probe_row(t, at, quote))
            params_rec = {"grid": chunk.timeframe, "latency_seconds": PROBE_LATENCY_SECONDS, "lookback_seconds": PROBE_LOOKBACK_SECONDS,
                          "sort": "desc", "limit": 1, "feed": chunk.feed if not crypto else None, "probes": len(times)}
            if error == "budget":
                states[symbol] = "skipped"
                continue
            if error:
                self.store.commit_chunk(chunk, symbol, state="failed", run=run, error=error, params=params_rec, calls=calls)
                states[symbol] = "failed"
                continue
            settled = _ts(chunk.end) <= self.clock() - SETTLE_SECONDS
            present = [r for r in rows if r[2] is not None]
            state = ("done" if present else "empty") if settled else "open"
            self.store.commit_chunk(chunk, symbol, state=state, rows=rows, table="probes", params=params_rec, calls=calls, run=run,
                                    first_t=rows[0][0] if rows else None, last_t=rows[-1][0] if rows else None)
            states[symbol] = state
            with self._tally_lock:
                self.tally.rows += len(rows)
        return states

    def trade_plan(self, symbols: Sequence[str], since: "str | date", until: "str | date | None" = None, *, grid: str = "1Hour") -> list[Chunk]:
        return [Chunk("trades", c.symbols, grid, c.feed, "raw", c.start, c.end)
                for c in self.probe_plan([s for s in symbols if not is_crypto(s)], since, until, grid=grid)]

    def fetch_trades(self, chunk: Chunk, symbols: Sequence[str], run: "str | None" = None) -> dict[str, str]:
        """The prints in the first `TRADE_WINDOW_SECONDS` after each grid close of the session:
        what a resting limit would have had to trade against."""
        states = {}
        for symbol in symbols:
            try:
                times = self.probe_times(chunk, symbol)
            except BudgetSpent:
                states[symbol] = "skipped"
                continue
            except VenueFailure as exc:
                self.store.commit_chunk(chunk, symbol, state="failed", run=run, error=f"calendar: {exc}", params={})
                states[symbol] = "failed"
                continue
            rows, calls, error = [], 0, None
            for t in times:
                if t + TRADE_WINDOW_SECONDS > self.clock():
                    break
                params = {"symbols": symbol, "start": iso(t), "end": iso(t + TRADE_WINDOW_SECONDS), "limit": PAGE_LIMIT, "feed": chunk.feed}
                try:
                    found, used = self._paged(DATA_URL, STOCK_TRADES_PATH, params, "trades")
                except BudgetSpent:
                    error = "budget"
                    break
                except VenueFailure as exc:
                    error = str(exc)
                    break
                calls += used
                for trade in found.get(symbol, []):
                    parsed = _trade_row(trade)
                    if parsed is not None:
                        rows.append(parsed)
            params_rec = {"grid": chunk.timeframe, "window_seconds": TRADE_WINDOW_SECONDS, "feed": chunk.feed, "windows": len(times)}
            if error == "budget":
                states[symbol] = "skipped"
                continue
            if error:
                self.store.commit_chunk(chunk, symbol, state="failed", run=run, error=error, params=params_rec, calls=calls)
                states[symbol] = "failed"
                continue
            settled = _ts(chunk.end) <= self.clock() - SETTLE_SECONDS
            state = ("done" if rows else "empty") if settled else "open"
            self.store.commit_chunk(chunk, symbol, state=state, rows=rows, table="trades", params=params_rec, calls=calls, run=run,
                                    first_t=rows[0][0] // 1_000_000_000 if rows else None, last_t=rows[-1][0] // 1_000_000_000 if rows else None)
            states[symbol] = state
            with self._tally_lock:
                self.tally.rows += len(rows)
        return states


def _iso_frac(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _bar_row(row: Any) -> "tuple | None":
    """A venue bar as a store row (t = its open, epoch seconds), or None when unusable."""
    if not isinstance(row, dict):
        return None
    try:
        opened = int(parse_time(row.get("t")))
    except TapeError:
        return None
    o, h, l, c = (_float(row.get(key)) for key in ("o", "h", "l", "c"))
    if o is None or h is None or l is None or c is None or min(o, h, l, c) <= 0:
        return None
    n = row.get("n")
    return (opened, o, h, l, c, max(0.0, _float(row.get("v")) or 0.0),
            int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else None, _float(row.get("vw")))


def _probe_row(t: int, at: float, quote: Any) -> tuple:
    """(t, at, quote_ns, bp, bs, ap, as, bx, ax, c): an absent or one-sided quote keeps its NULLs."""
    if not isinstance(quote, dict):
        return (t, at, None, None, None, None, None, None, None, None)
    conditions = quote.get("c")
    return (t, at, _ns(quote.get("t")), _float(quote.get("bp")), _float(quote.get("bs")), _float(quote.get("ap")),
            _float(quote.get("as")), quote.get("bx"), quote.get("ax"),
            ",".join(str(c) for c in conditions) if isinstance(conditions, list) else None)


def _trade_row(trade: Any) -> "tuple | None":
    if not isinstance(trade, dict):
        return None
    stamp, price, size = _ns(trade.get("t")), _float(trade.get("p")), _float(trade.get("s"))
    if stamp is None or price is None or size is None or price <= 0:
        return None
    conditions = trade.get("c")
    return (stamp, str(trade.get("i", "")), str(trade.get("x", "")), price, size,
            ",".join(str(c) for c in conditions) if isinstance(conditions, list) else None)


# ------------------------------------------------------------- the ledger row

#: A running ingestion is summarised in the ledger at most this often.
PROGRESS_SECONDS = 3600.0


def coverage_payload(store: HistoryStore, run: Mapping[str, Any]) -> dict[str, Any]:
    """The `data.coverage` row for one run: what it did, and what the whole store now holds."""
    series = []
    for item in store.summary():
        series.append({key: item[key] for key in ("kind", "symbol", "timeframe", "feed", "adjustment", "done", "empty",
                                                  "open", "failed", "rows", "first_day", "last_day", "fetched_at")})
    try:
        args = json.loads(run.get("args") or "{}")
    except ValueError:
        args = {}
    return {
        "source": SOURCE, "run": run["run"], "status": run["status"],
        "started_at": iso(run["started_at"]), "finished_at": iso(run["finished_at"]) if run.get("finished_at") else None,
        "args": args, "calls": int(run.get("calls") or 0), "rows": int(run.get("rows") or 0),
        "chunks": json.loads(run.get("chunks") or "{}"), "store": f"{HISTORY_DIR}/{DB_NAME}",
        "series": series[:600], "limitations": list(LIMITATIONS),
        "states": {"empty": "unavailable: the venue returned nothing", "absent": "unfetched: a gap in the store, not a market fact"},
    }


def publish_coverage(ledger: Any, root: "str | Path", *, clock: Callable[[], float] = time.time) -> int:
    """Append a `data.coverage` row for every ingestion run that ended since the last call, and
    an hourly progress row for one still running. Idempotent: the row id names the run (and the
    hour, for progress), and a run already recorded is skipped. Returns rows appended."""
    path = Path(root) / HISTORY_DIR / DB_NAME
    if not path.exists():
        return 0
    store = HistoryStore(path, readonly=True)
    appended = 0
    try:
        for run in store.runs():
            if run["status"] == "running" and _alive(run["pid"]):
                bucket = int(clock() // PROGRESS_SECONDS)
                key = f"data.coverage:{run['run']}:progress:{bucket}"
            else:
                if run["status"] == "running":
                    run = {**run, "status": "interrupted"}
                key = f"data.coverage:{run['run']}:final"
            if ledger.get(key) is not None:
                continue
            ledger.append("data.coverage", coverage_payload(store, run), id=key)
            appended += 1
    finally:
        store.close()
    return appended


# ------------------------------------------------------------------------ cli

def _client(config: Mapping[str, Any]) -> Any:
    from ltcm.adapters import GatewaySigner, VenueClient

    from .service import secret

    return VenueClient(None, gateway_url=config["gateway_url"], gateway=GatewaySigner(secret("GATEWAY_TOKEN")),
                       venue="alpaca-paper", timeout=60.0)


def main(argv: "Sequence[str] | None" = None, *, client: Any = None) -> int:
    from .service import REPO, load_config, load_env

    parser = argparse.ArgumentParser(prog="python -m league.history", description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["ingest", "coverage"])
    parser.add_argument("--root", default=str(REPO / ".data" / "league"), help="the House state directory")
    parser.add_argument("--universe", default="core", choices=["tier1", "core", "all"])
    parser.add_argument("--symbols", default="", help="comma-separated symbols instead of a universe")
    parser.add_argument("--timeframes", default="1Day,1Hour", help="comma-separated: 1Day,1Hour,5Min")
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--until", default=None)
    parser.add_argument("--max-minutes", type=float, default=None)
    parser.add_argument("--max-calls", type=int, default=None,
                        help="stop scheduling after this many venue calls (every call also passes through the gateway Worker)")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE, help="calls a minute (the plan allows 10,000)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--feed", default=None, help="stock feed; default: league/config.json alpaca_feed")
    parser.add_argument("--quotes", default="", help="quote probes for these symbols ('set' = the default small liquid set)")
    parser.add_argument("--quote-since", default=None, help="first day of quote probes (default: 200 days ago)")
    parser.add_argument("--quote-until", default=None, help="day after the last day of quote probes (default: today)")
    parser.add_argument("--quote-grid", default="5Min", help="equity probe grid inside the regular session")
    parser.add_argument("--crypto-grid", default="15Min", help="crypto probe grid over the whole day")
    parser.add_argument("--trades", default="", help="trade windows for these symbols ('set' = the equity quote set)")
    parser.add_argument("--refresh-adjusted", action="store_true",
                        help="fetch every split/dividend-adjusted chunk again (after a corporate action)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "coverage":
        # Read-only: it is run on the House box beside a live ingestion and must change nothing.
        path = Path(args.root) / HISTORY_DIR / DB_NAME
        if not path.exists():
            print(f"no history store at {path}")
            return 1
        store = HistoryStore(path, readonly=True)
        rows = store.summary()
        if args.json:
            print(json.dumps({"series": rows, "runs": store.runs()}, indent=1, default=str))
        else:
            for run in store.runs()[-5:]:
                print(f"run {run['run']} {run['status']} calls={run['calls']} rows={run['rows']} chunks={run['chunks']}")
            for row in rows:
                print(f"{row['kind']:7} {row['symbol']:9} {row['timeframe']:6} {row['feed']:5} {row['adjustment']:4} "
                      f"done={row['done'] or 0} empty={row['empty'] or 0} open={row['open'] or 0} failed={row['failed'] or 0} "
                      f"rows={row['rows'] or 0} {row['first_day'] or '-'}..{row['last_day'] or '-'}")
        store.close()
        return 0

    store = HistoryStore.at_root(args.root)
    load_env()
    config = load_config()
    feed = args.feed or config.get("alpaca_feed", "iex")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or universe(args.universe)
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    stamp = lambda text: print(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  {text}", flush=True)  # noqa: E731
    ingestor = Ingestor(store, client or _client(config), feed=feed, rate_per_minute=args.rate, workers=args.workers, log=stamp,
                        refresh_adjusted_before=time.time() if args.refresh_adjusted else None)
    run = store.begin_run({**vars(args), "feed": feed, "symbols": symbols, "timeframes": timeframes})
    stop = threading.Event()
    status, error = "finished", None
    try:
        import signal

        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except (ValueError, OSError):  # not the main thread (tests)
        pass
    try:
        started = time.monotonic()
        chunks = ingestor.plan(symbols, timeframes, args.since, args.until)
        quote_symbols = list(QUOTE_SET) if args.quotes == "set" else [s.strip().upper() for s in args.quotes.split(",") if s.strip()]
        trade_symbols = [s for s in QUOTE_SET if not is_crypto(s)] if args.trades == "set" else [s.strip().upper() for s in args.trades.split(",") if s.strip()]
        quote_since = args.quote_since or str((datetime.now(timezone.utc) - timedelta(days=200)).date())
        chunks += ingestor.probe_plan(quote_symbols, quote_since, args.quote_until, grid=args.quote_grid,
                                      crypto_grid=args.crypto_grid) if quote_symbols else []
        chunks += ingestor.trade_plan(trade_symbols, quote_since, args.quote_until) if trade_symbols else []
        stamp(f"run {run}: {len(chunks)} chunks planned for {len(symbols)} symbols, {timeframes}, since {args.since}, feed {feed}")
        tally = ingestor.run(chunks, run=run, max_minutes=args.max_minutes, stop=stop, max_calls=args.max_calls)
        # An `open` chunk (it reaches into the present) is fetched again on every run by design;
        # only a chunk never fetched, or failed, means this run stopped short.
        remaining = sum(1 for chunk in chunks for symbol in chunk.symbols
                        if store.chunk_state(chunk.kind, symbol, chunk.timeframe, chunk.feed, chunk.adjustment,
                                             chunk.start, chunk.end) in (None, "failed"))
        if remaining:
            status = "stopped"
        stamp(f"run {run} {status}: {tally.calls} calls, {tally.rows} rows, chunks {tally.chunks}, {remaining} chunks unfetched or failed, "
              f"{(time.monotonic() - started) / 60:.1f} min")
    except BaseException as exc:  # noqa: BLE001 - the run row must say how it ended
        status, error = ("stopped" if isinstance(exc, KeyboardInterrupt) else "failed"), f"{type(exc).__name__}: {exc}"
        raise
    finally:
        store.progress_run(run, calls=ingestor.tally.calls, rows=ingestor.tally.rows, chunks=ingestor.tally.chunks)
        store.finish_run(run, status, error=error)
        store.close()
    return 0 if status in ("finished", "stopped") else 1


if __name__ == "__main__":
    sys.exit(main())

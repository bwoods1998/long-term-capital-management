"""Listed-option history: a resumable store, the replay tape of the options desk, and the
options-derived features the equity and ETF desks may read.

WHAT ALPACA ACTUALLY PROVIDES (measured through the gateway, Sept 22, 2026):

- `GET /v2/options/contracts` lists contracts of an underlying, EXPIRED ones included
  (`status=inactive`), back to at least January 2024. There is no listing date. An expired row
  carries `multiplier: "0"` and `size: "100"`, its last `close_price` and its last
  `open_interest` (as of the day before expiry): neither is point in time, so neither is used.
- `GET /v1beta1/options/bars` returns OPRA trade bars (`o h l c v n vw`, `n` the trade count) at
  1Min to 1Day. The first bar of any contract probed is 2024-01-18: nothing earlier exists.
  A bar exists only where the contract printed; a quiet interval is simply absent.
- `GET /v1beta1/options/trades` (historical prints) exists at Alpaca, but the gateway does not
  sign the path (403 "Not a path this gateway signs"), so prints are UNAVAILABLE until the
  gateway allows it. This module records that as coverage, never as zero trades.
- There is NO historical option QUOTE endpoint at all (Alpaca's reference lists historical bars
  and trades, and latest quotes, trades and snapshots only). Every historical bid and ask this
  module produces is therefore an ESTIMATE from trade prints and bar ranges (`estimate_quote`),
  labelled as such on every row; the tape's `spread_model.stress` widens what fills pay.
- Greeks, implied volatility and open interest have no history. The live snapshot's vendor
  greeks are not stored; what is here is COMPUTED (Black-Scholes, below) from prints.

THREE RULES KEEP IT HONEST.

1. **Nothing is fabricated.** A contract with no bar in a window is `unavailable` there, not a
   zero-volume contract; a chunk the venue refused is recorded with its error, and a later
   `ingest` tries it again. Coverage is written to the ledger as `data.coverage` rows with
   `asset: "option"` and to this store's `coverage` table.
2. **Point in time.** The venue gives no listing date, so a contract is taken to EXIST at `t`
   only once it has printed at or before `t` (its first bar's close). That hides contracts that
   were listed but had not yet traded -- conservative: a live chain would show them -- and never
   shows one before it existed. A contract never exists after its expiry.
3. **No lookahead in selection.** Which contracts are downloaded depends on the underlying's
   price range over each contract's own life, widened by `band`; the chain shown at `t` is
   filtered again by the price AT `t` (within 20% of it, as `House._chain`). The download is a
   superset of every chain a step could show, so selection cannot leak the future.

Standard library only; floats (this is statistics, not the money ledger).
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SOURCE_BARS = "alpaca:/v1beta1/options/bars (OPRA trade bars)"
SOURCE_CONTRACTS = "alpaca:/v2/options/contracts (active and inactive)"
SOURCE_TRADES = "alpaca:/v1beta1/options/trades (OPRA prints)"
#: The first option bar Alpaca holds for any contract probed (Sept 22, 2026).
HISTORY_STARTS = "2024-01-18"
TIMEFRAMES = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400}
BATCH = 100  # option symbols per bars request
PAGE_LIMIT = 10_000
#: Contracts per listing page. SPY's listing at 10,000 a page is over the 4 MB the venue client
#: accepts (measured Sept 22, 2026: the whole SPY/QQQ ingestion was refused for it).
CONTRACT_PAGE = 1_000
MAX_PAGES = 400
MULTIPLIER = 100
OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")

#: Black-Scholes inputs that are ASSUMED, not given (labelled on every feature row).
RISK_FREE = 0.04  # roughly the 2024-2026 T-bill rate; a constant, not a curve
DIVIDEND_YIELD = 0.0
FEATURE_VERSION = "bs-close-v2"  # v2: the underlying close is unadjusted (v1 used dividend-adjusted closes)

#: The replay's estimated-quote model (labelled and stressed; see `estimate_quote` and
#: `display_quote`). Two estimates, on purpose: what a strategy is SHOWN (and marked at) is a
#: central estimate fitted to the median live OPRA spread, so its decisions and stops meet the
#: market they would meet live; what a FILL at the touch pays is the wider, conservative one.
SPREAD_MODEL = {
    "kind": "estimated from trade prints and bar ranges: no historical option quotes exist",
    # Shown and marked: last print +- max(display_min_half, display_pct x premium). Fitted on
    # Sept 22, 2026 to 871 live OPRA quotes of the desk's six underlyings in the session's first
    # hour; checked on 1,190: its median half-spread equals the quoted median and it is at least
    # as wide 60.5% of the time.
    "display_min_half": 0.01,
    "display_pct": 0.045,
    # Paid by a fill at the touch (below): at least as wide as the quoted half-spread 76.6% of the
    # time on the same 1,190 quotes, with a median about twice the quoted one.
    "min_half_ticks": 1.0,     # at least one tick either side of the last print
    "floor_pct": 0.04,         # half-spread at least 4% of the premium (live Sept 19: 8-100 of 60-900 contracts under a 15% spread)
    "range_weight": 0.5,       # half the median high-low range of the contract's last printed bars
    "range_bars": 5,
    # Half-spread floors by premium, from live OPRA quotes of the desk's six underlyings
    # (`measured_floors`; see MEASURED_SPREADS). [max premium, floor], checked in order.
    "measured_floors": [],
    # EXECUTION stress: multiplies the half-spread a fill at the touch pays, never the quote a
    # strategy is shown -- so a stressed run changes costs and not the strategy's decisions.
    "stress": 1.0,
    # The fill half-spread CALIBRATED on recorded OPRA quotes (`CALIBRATED_SPREADS`, `calibrated_half`):
    # None (the default) keeps the estimate above; a calibration table replaces it wherever the table
    # has a bucket measured on enough quotes. `stress` still multiplies whatever a fill pays.
    "calibration": None,
}
#: A structure tape keeps a contract's bar only within this fraction of the underlying's price then:
#: the chain's own moneyness line (`House._chain`), so nothing a structure agent could be shown is lost.
STRUCTURE_BAND = 0.20
#: The most option bars a structure tape carries. Measured Sept 25, 2026 on the local copy: SPY, QQQ and
#: IWM at 0-7 days over the House's whole options window (May 16 to Sept 24, 2,340 steps) are 797,000
#: bars, 43 MB of JSON, 323 MB resident and 125 s of CPU on a laptop at load 40, whose CPU ran the same
#: Black-Scholes loop 6-8x slower than the House box's; so this cap is about 110 MB and a minute of a
#: box's CPU, well inside its 2 GB and 300 s.
STRUCTURE_TAPE_MAX_BARS = 2_000_000
LIQUIDITY = {"min_volume": 5.0, "min_trades": 2, "max_participation": 0.10, "quote_age_seconds": 1500}
#: Alpaca charges no options commission (`league/fees.py`); the regulatory and clearing
#: pass-through (ORF, OCC, TAF) is not yet measured on this account. Assumed, per contract per fill.
FEE_PER_CONTRACT_USD = 0.05


class HistoryError(RuntimeError):
    """The venue refused or could not answer; the chunk stays unfinished."""


# ------------------------------------------------------------------------------ small helpers
def parse_occ(occ: str) -> dict[str, Any] | None:
    match = OCC.match(str(occ or "").upper())
    if not match:
        return None
    root, ymd, right, strike = match.groups()
    return {"occ": str(occ).upper(), "underlying": root, "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:]}",
            "right": "call" if right == "C" else "put", "strike": int(strike) / 1000.0}


def _ts(value: Any) -> float:
    text = str(value).strip().replace("Z", "+00:00").replace("z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    moment = datetime.fromisoformat(text)
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_date(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), NY).strftime("%Y-%m-%d")


def _day(text: str) -> date:
    return date.fromisoformat(str(text)[:10])


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def close_stamp(open_t: str, timeframe: str) -> str:
    """A bar stamped with the moment it closed (as `league/tapes.py`): a daily bar at the NY
    midnight after its session, so a strategy cannot read a close before the day is over."""
    opened = _ts(open_t)
    if timeframe == "1Day":
        day = datetime.fromtimestamp(opened, NY).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return iso(day.timestamp())
    return iso(opened + TIMEFRAMES[timeframe])


def tick(price: float) -> float:
    """The penny-program minimum increment: $0.01 under $3, $0.05 at and above (SPY, QQQ and
    IWM quote in pennies throughout; treating them as nickels above $3 is conservative)."""
    return 0.01 if price < 3.0 else 0.05


# ------------------------------------------------------------------------------ Black-Scholes
def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, years: float, vol: float, right: str, *, rate: float = RISK_FREE, q: float = DIVIDEND_YIELD) -> float:
    """European Black-Scholes. Listed equity options are American; for the short-dated, near
    the money, long-premium contracts here the early-exercise premium is small (a labelled
    approximation, largest for deep in-the-money puts)."""
    if years <= 0 or vol <= 0:
        intrinsic = spot - strike if right == "call" else strike - spot
        return max(0.0, intrinsic)
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - q + 0.5 * vol * vol) * years) / sq
    d2 = d1 - sq
    if right == "call":
        return spot * math.exp(-q * years) * _cdf(d1) - strike * math.exp(-rate * years) * _cdf(d2)
    return strike * math.exp(-rate * years) * _cdf(-d2) - spot * math.exp(-q * years) * _cdf(-d1)


def bs_delta(spot: float, strike: float, years: float, vol: float, right: str, *, rate: float = RISK_FREE, q: float = DIVIDEND_YIELD) -> float:
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - q + 0.5 * vol * vol) * years) / sq
    return math.exp(-q * years) * (_cdf(d1) if right == "call" else _cdf(d1) - 1.0)


def implied_vol(price: float, spot: float, strike: float, years: float, right: str, *, rate: float = RISK_FREE,
                q: float = DIVIDEND_YIELD, low: float = 0.005, high: float = 5.0) -> float | None:
    """The volatility at which Black-Scholes gives `price`, by bisection (monotone in vol). None
    when the price is outside what any volatility in [low, high] can produce -- under the
    discounted intrinsic value, or a stale print -- rather than a number made up to fit."""
    if not (price > 0 and spot > 0 and strike > 0 and years > 0):
        return None
    # `bs_price` with what does not depend on the volatility worked out once: the same operations in
    # the same order, so the same bits, at half the cost (the options replay solves one a shown print;
    # this was two thirds of a structure replay's time, Sept 25, 2026).
    root, moneyness, carry, grow, discount = math.sqrt(years), math.log(spot / strike), (rate - q), math.exp(-q * years), math.exp(-rate * years)

    def value(vol: float) -> float:
        sq = vol * root
        d1 = (moneyness + (carry + 0.5 * vol * vol) * years) / sq
        d2 = d1 - sq
        if right == "call":
            return spot * grow * _cdf(d1) - strike * discount * _cdf(d2)
        return strike * discount * _cdf(-d2) - spot * grow * _cdf(-d1)

    if not value(low) < price < value(high):
        return None
    for _ in range(80):
        mid = 0.5 * (low + high)
        if value(mid) < price:
            low = mid
        else:
            high = mid
        if high - low < 1e-7:
            break
    return 0.5 * (low + high)


def years_to(expiry: str, at_ts: float) -> float:
    """Year fraction from `at_ts` to 16:00 New York on the expiry date."""
    close = datetime.combine(_day(expiry), datetime.min.time(), NY).replace(hour=16).timestamp()
    return max(0.0, (close - at_ts) / (365.0 * 86400.0))


# ------------------------------------------------------------------------------ quote estimate
def display_quote(last: float, model: Mapping[str, Any] | None = None) -> tuple[float | None, float]:
    """`(bid, ask)` a replay SHOWS around a last print: the central estimate (see SPREAD_MODEL).
    The bid is None when it would be zero or less."""
    m = {**SPREAD_MODEL, **dict(model or {})}
    half = max(float(m["display_min_half"]), float(m["display_pct"]) * float(last))
    bid = round(float(last) - half, 4)
    return (bid if bid > 0 else None), round(float(last) + half, 4)


def spread_bucket(calibration: Mapping[str, Any], underlying: str, last: float, strike: float | None, spot: float | None) -> dict[str, Any] | None:
    """The calibration bucket of a contract: its class (the table's `etf` underlyings, or a single stock),
    its last print's premium, and at a premium of $3 or more its moneyness |strike / spot - 1| (deep in
    the money index options are quoted dollars wide: Sept 22-24, 2026). None where no bucket fits."""
    kind = "etf" if str(underlying or "").upper() in set(calibration.get("etf") or ()) else "stock"
    away = abs(float(strike) / float(spot) - 1.0) if strike and spot else None
    for row in calibration.get("buckets") or ():
        low, high = row["premium"]
        if row["class"] != kind or not (low <= last and (high is None or last < high)):
            continue
        band = row.get("moneyness")
        if band is not None:
            if away is None or not (band[0] <= away and (band[1] is None or away < band[1])):
                continue
        return dict(row)
    return None


def calibrated_half(calibration: Mapping[str, Any] | None, underlying: str, last: float, strike: float | None = None,
                    spot: float | None = None) -> float | None:
    """The calibrated fill half-spread of a leg printed last at `last`, or None (the estimate then) when
    the calibration is off, has no bucket for it, or measured its bucket on fewer than `min_quotes`."""
    if not calibration:
        return None
    row = spread_bucket(calibration, underlying, float(last), strike, spot)
    if row is None or int(row.get("quotes") or 0) < int(calibration.get("min_quotes") or 0):
        return None
    return float(row["half"])


def estimate_quote(bar: Mapping[str, Any], recent_ranges: Sequence[float], model: Mapping[str, Any] | None = None, *,
                   contract: Mapping[str, Any] | None = None, spot: float | None = None) -> tuple[float | None, float, float]:
    """`(bid, ask, half)` a FILL at the touch pays, estimated around a bar's last print: the
    conservative estimate. There are no historical quotes, so the half-spread is the largest of
    one tick, `floor_pct` of the premium, `range_weight` of the median high-low range of the
    contract's last printed bars (prints bounce between bid and ask) and any measured floor. The
    bid is None when it would be zero or less. (`stress` is applied by the replay, to fills.)

    Measured Sept 22, 2026 against 1,190 live OPRA quotes of the desk's six underlyings in the
    session's first hour (the House's recorded quotes let `spread_check` repeat this every day):
    at least as wide as the quoted half-spread 76.6% of the time, 68% to 87% by premium bucket,
    with a median about twice the quoted median."""
    m = {**SPREAD_MODEL, **dict(model or {})}
    last = float(bar["c"])
    if m.get("calibration") and contract is not None:
        # The calibrated half-spread (`CALIBRATED_SPREADS`), never under a tick; the estimate below
        # where the table has no measured bucket for this contract.
        measured = calibrated_half(m["calibration"], str(contract.get("underlying") or ""), last, _float(contract.get("strike")), spot)
        if measured is not None:
            half = round(max(m["min_half_ticks"] * tick(last), measured), 4)
            bid = round(last - half, 4)
            return (bid if bid > 0 else None), round(last + half, 4), half
    ranges = sorted(float(r) for r in recent_ranges if r is not None and r >= 0)
    median = ranges[len(ranges) // 2] if ranges else 0.0
    floor = next((float(f) for cap, f in (m.get("measured_floors") or []) if last < float(cap)), 0.0)
    half = max(m["min_half_ticks"] * tick(last), m["floor_pct"] * last, m["range_weight"] * median, floor)
    half = round(half, 4)
    bid = round(last - half, 4)
    return (bid if bid > 0 else None), round(last + half, 4), half


# ------------------------------------------------------------------------------ the store
SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (occ TEXT PRIMARY KEY, underlying TEXT NOT NULL, expiry TEXT NOT NULL,
    strike REAL NOT NULL, right TEXT NOT NULL, size INTEGER, status TEXT, fetched_at TEXT);
CREATE INDEX IF NOT EXISTS contracts_by_underlying ON contracts(underlying, expiry);
CREATE TABLE IF NOT EXISTS bars (occ TEXT NOT NULL, timeframe TEXT NOT NULL, t TEXT NOT NULL,
    o REAL, h REAL, l REAL, c REAL, v REAL, n INTEGER, vw REAL, PRIMARY KEY (occ, timeframe, t));
CREATE TABLE IF NOT EXISTS trades (occ TEXT NOT NULL, t TEXT NOT NULL, p REAL, s REAL, x TEXT, c TEXT,
    PRIMARY KEY (occ, t, p, s, x));
CREATE TABLE IF NOT EXISTS quotes (occ TEXT NOT NULL, t TEXT NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
    source TEXT NOT NULL, PRIMARY KEY (occ, t));
CREATE TABLE IF NOT EXISTS chunks (key TEXT PRIMARY KEY, state TEXT NOT NULL, rows INTEGER, at TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS coverage (key TEXT PRIMARY KEY, payload TEXT NOT NULL, at TEXT);
CREATE TABLE IF NOT EXISTS features (symbol TEXT NOT NULL, day TEXT NOT NULL, version TEXT NOT NULL,
    available_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (symbol, day, version));
"""


def _retrying(call: Callable[[], Any], *, attempts: int = 3, pause: float = 2.0) -> Any:
    """A market-data GET is idempotent: a read that timed out is asked again, twice, before the
    chunk is marked failed (measured Sept 22, 2026: under load the gateway timed out a one-page
    daily-bar read that succeeded seconds later)."""
    for attempt in range(attempts):
        try:
            return call()
        except HistoryError:
            raise  # the venue answered, and said no
        except Exception as exc:  # noqa: BLE001 - a transport failure
            if attempt == attempts - 1 or "HTTP 4" in str(exc):
                raise  # the last attempt, or a refusal the gateway or venue gave
            time.sleep(pause * (attempt + 1))


def gateway_get(broker: Any) -> Callable[[str, Mapping[str, Any]], Any]:
    """`get(path, params)` through an `AlpacaBroker` in gateway mode: the market-data host for
    `/v1beta1`, the trading host for `/v2/options/contracts` (the gateway picks the host)."""
    def get(path: str, params: Mapping[str, Any]) -> Any:
        base = broker.data if path.startswith("/v1beta") else broker.base
        pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
        url = base + path + ("?" + urllib.parse.urlencode(pairs, safe=",:") if pairs else "")
        status, payload = _retrying(lambda: broker.client.request("GET", url, headers={}, what=f"options history {path}"))
        if status != 200:
            detail = payload.get("error") or payload.get("message") if isinstance(payload, dict) else str(payload)[:200]
            raise HistoryError(f"HTTP {status} {detail}")
        return payload
    return get


class OptionsHistory:
    """The resumable, cached store. `get(path, params) -> payload` is the only way out."""

    def __init__(self, path: str | Path, get: Callable[[str, Mapping[str, Any]], Any] | None = None, *,
                 ledger: Any = None, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.get = get
        self.ledger = ledger
        self.clock = clock
        self._lock = threading.RLock()  # one writer at a time in this process
        self._local = threading.local()
        self._connections: list[tuple[threading.Thread, Any]] = []
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    @property
    def db(self) -> Any:
        """This thread's connection. The House reads the store from wake threads (quotes,
        features), the replay lane (tapes) and the ops lane (the daily job) at once, and one
        sqlite3 connection must not be shared between threads that use it concurrently. WAL
        lets readers go on while the daily job writes."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            # Used only by this thread; closable by any (a wake thread's connection is closed
            # here once its thread has ended: the House makes new wake threads every tick).
            import sqlite3  # here, not at the top: the agent's box imports this file for its pure functions only

            conn = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
            with self._lock:
                for thread, old in [pair for pair in self._connections if not pair[0].is_alive()]:
                    old.close()
                self._connections = [pair for pair in self._connections if pair[0].is_alive()]
                self._connections.append((threading.current_thread(), conn))
        return conn

    def close(self) -> None:
        with self._lock:
            for _, conn in self._connections:
                conn.close()
            self._connections = []
        self._local = threading.local()

    # -- resumable chunks --------------------------------------------------------------------
    def done(self, key: str) -> bool:
        row = self.db.execute("SELECT state FROM chunks WHERE key = ?", (key,)).fetchone()
        return bool(row and row[0] == "done")

    def _mark(self, key: str, state: str, rows: int, detail: str = "") -> None:
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?)", (key, state, rows, iso(self.clock()), detail[:400]))
            self.db.commit()

    def _pages(self, path: str, params: dict[str, Any], field: str) -> Iterable[Any]:
        if self.get is None:
            raise HistoryError("no venue access: this store is read-only")
        token = None
        for _ in range(MAX_PAGES):
            payload = self.get(path, {**params, "page_token": token})
            if not isinstance(payload, dict):
                raise HistoryError(f"{path}: the response is not an object")
            yield payload.get(field)
            token = payload.get("next_page_token")
            if not token:
                return
        raise HistoryError(f"{path}: more than {MAX_PAGES} pages")

    # -- contracts ---------------------------------------------------------------------------
    def list_contracts(self, underlying: str, expiry_from: str, expiry_to: str, *, strike_from: float | None = None,
                       strike_to: float | None = None) -> int:
        """Store every contract of `underlying` expiring in [expiry_from, expiry_to], expired and
        live. A chunk whose window reaches today is refetched next time (new strikes list)."""
        underlying = underlying.upper()
        key = f"contracts:{underlying}:{expiry_from}:{expiry_to}:{strike_from}:{strike_to}"
        if self.done(key):
            return 0
        rows = 0
        now = iso(self.clock())
        for status in ("inactive", "active"):
            params = {"underlying_symbols": underlying, "status": status, "expiration_date_gte": expiry_from,
                      "expiration_date_lte": expiry_to, "limit": CONTRACT_PAGE,
                      "strike_price_gte": None if strike_from is None else f"{strike_from:.2f}",
                      "strike_price_lte": None if strike_to is None else f"{strike_to:.2f}"}
            for page in self._pages("/v2/options/contracts", params, "option_contracts"):
                batch = []
                for row in page or []:
                    parsed = parse_occ(row.get("symbol")) if isinstance(row, dict) else None
                    if parsed is None or parsed["underlying"] != underlying:
                        continue  # an adjusted contract (a root like F1) is a different deliverable
                    batch.append((parsed["occ"], underlying, parsed["expiry"], parsed["strike"], parsed["right"],
                                  int(_float(row.get("size")) or MULTIPLIER), str(row.get("status") or status), now))
                with self._lock:
                    self.db.executemany("INSERT OR REPLACE INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", batch)
                    self.db.commit()
                rows += len(batch)
        final = _day(expiry_to) < _day(ny_date(self.clock()))
        self._mark(key, "done" if final else "partial", rows)
        return rows

    def contracts(self, underlying: str, expiry_from: str = "0000", expiry_to: str = "9999") -> list[dict[str, Any]]:
        cur = self.db.execute("SELECT occ, underlying, expiry, strike, right, size FROM contracts WHERE underlying = ? AND expiry >= ? AND expiry <= ? ORDER BY expiry, strike, right",
                              (underlying.upper(), expiry_from, expiry_to))
        return [dict(zip(("occ", "underlying", "expiry", "strike", "right", "size"), r)) for r in cur]

    # -- bars and trades ---------------------------------------------------------------------
    def fetch_bars(self, occs: Sequence[str], timeframe: str, start: str, end: str) -> int:
        """Bars of these contracts whose OPEN is in [start, end], stored close-stamped."""
        stored = 0
        for i in range(0, len(occs), BATCH):
            group = list(occs[i:i + BATCH])
            params = {"symbols": ",".join(group), "timeframe": timeframe, "start": start, "end": end, "limit": PAGE_LIMIT, "sort": "asc"}
            for page in self._pages("/v1beta1/options/bars", params, "bars"):
                batch = []
                for occ, rows in (page or {}).items():
                    for row in rows or []:
                        o, h, l, c = (_float(row.get(k)) for k in "ohlc")
                        if None in (o, h, l, c) or min(o, h, l, c) <= 0 or not row.get("t"):
                            continue
                        batch.append((str(occ).upper(), timeframe, close_stamp(row["t"], timeframe), o, h, l, c,
                                      max(0.0, _float(row.get("v")) or 0.0), int(_float(row.get("n")) or 0), _float(row.get("vw"))))
                with self._lock:
                    self.db.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
                    self.db.commit()
                stored += len(batch)
        return stored

    def fetch_trades(self, occs: Sequence[str], start: str, end: str) -> int:
        stored = 0
        for i in range(0, len(occs), BATCH):
            params = {"symbols": ",".join(occs[i:i + BATCH]), "start": start, "end": end, "limit": PAGE_LIMIT, "sort": "asc"}
            for page in self._pages("/v1beta1/options/trades", params, "trades"):
                batch = [(str(occ).upper(), str(r.get("t")), _float(r.get("p")), _float(r.get("s")), str(r.get("x") or ""), str(r.get("c") or ""))
                         for occ, rows in (page or {}).items() for r in rows or [] if r.get("t")]
                with self._lock:
                    self.db.executemany("INSERT OR IGNORE INTO trades VALUES (?, ?, ?, ?, ?, ?)", batch)
                    self.db.commit()
                stored += len(batch)
        return stored

    def bars(self, occs: Sequence[str], timeframe: str, start: str = "", end: str = "9999") -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for i in range(0, len(occs), 500):
            group = list(occs[i:i + 500])
            marks = ",".join("?" * len(group))
            cur = self.db.execute(f"SELECT occ, t, o, h, l, c, v, n, vw FROM bars WHERE timeframe = ? AND t >= ? AND t <= ? AND occ IN ({marks}) ORDER BY occ, t",
                                  (timeframe, start, end, *group))
            for occ, t, o, h, l, c, v, n, vw in cur:
                out.setdefault(occ, []).append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "n": n, "vw": vw})
        return out

    # -- recorded live quotes ------------------------------------------------------------------
    def record_quotes(self, rows: Iterable[Mapping[str, Any]], *, source: str) -> int:
        """Keep the two-sided OPRA quotes the House already read for a live chain (no extra
        call). From Sept 22, 2026 on this is a real quote history: a replay over those days uses
        it instead of an estimate, and `spread_check` measures the estimate against it. Only
        OPRA is kept: the older indicative feed's quotes were modified."""
        if source != "opra":
            return 0
        batch = []
        for row in rows:
            occ, bid, ask, stamp = str(row.get("symbol") or row.get("occ") or ""), _float(row.get("bid")), _float(row.get("ask")), row.get("as_of")
            if parse_occ(occ) and bid and ask and 0 < bid < ask and stamp and not str(stamp).startswith("1970"):
                batch.append((occ.upper(), iso(_ts(stamp)), bid, ask, source))
        with self._lock:
            self.db.executemany("INSERT OR IGNORE INTO quotes VALUES (?, ?, ?, ?, ?)", batch)
            self.db.commit()
        return len(batch)

    def quotes(self, occs: Sequence[str], start: str = "", end: str = "9999") -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for i in range(0, len(occs), 500):
            group = list(occs[i:i + 500])
            marks = ",".join("?" * len(group))
            for occ, t, bid, ask in self.db.execute(f"SELECT occ, t, bid, ask FROM quotes WHERE t >= ? AND t <= ? AND occ IN ({marks}) ORDER BY occ, t", (start, end, *group)):
                out.setdefault(occ, []).append({"t": t, "bid": bid, "ask": ask})
        return out

    def spread_check(self, timeframe: str = "15Min", model: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The execution estimate against recorded OPRA quotes: for each recorded quote, the
        estimate from the contract's last print at or before it (`share_conservative`: how often
        it was at least as wide), and the displayed estimate's share (`display_share_wider`,
        which should sit near a half)."""
        rows = []
        for occ, t, bid, ask in self.db.execute("SELECT occ, t, bid, ask FROM quotes ORDER BY occ, t"):
            bars = self.db.execute("SELECT o, h, l, c, v, n FROM bars WHERE occ = ? AND timeframe = ? AND t <= ? ORDER BY t DESC LIMIT 5",
                                   (occ, timeframe, t)).fetchall()
            if not bars:
                continue
            last = dict(zip(("o", "h", "l", "c", "v", "n"), bars[0]))
            _, _, half = estimate_quote(last, [b[1] - b[2] for b in bars], model)
            shown_bid, shown_ask = display_quote(last["c"], model)
            rows.append({"occ": occ, "premium": (bid + ask) / 2, "quoted_half": (ask - bid) / 2, "estimated_half": half,
                         "displayed_half": (shown_ask - (shown_bid if shown_bid is not None else 0.0)) / 2})
        wider = [r for r in rows if r["estimated_half"] >= r["quoted_half"] - 1e-9]
        shown = [r for r in rows if r["displayed_half"] >= r["quoted_half"] - 1e-9]
        return {"quotes_compared": len(rows), "estimate_at_least_as_wide": len(wider),
                "share_conservative": round(len(wider) / len(rows), 4) if rows else None,
                "display_share_wider": round(len(shown) / len(rows), 4) if rows else None}

    # -- coverage ----------------------------------------------------------------------------
    def record_coverage(self, row: dict[str, Any]) -> dict[str, Any]:
        row = {"asset": "option", **row, "recorded_at": iso(self.clock())}
        key = f"{row['asset']}:{row.get('underlying')}:{row.get('timeframe')}:{row.get('start')}:{row.get('end')}"
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO coverage VALUES (?, ?, ?)", (key, json.dumps(row, sort_keys=True), row["recorded_at"]))
            self.db.commit()
        if self.ledger is not None:
            try:
                self.ledger.append("data.coverage", row, id=f"coverage:{key}:{row.get('status')}:{row.get('bars')}")
            except Exception:  # noqa: BLE001 - the store is the record; the ledger row is the index
                pass
        return row

    def coverage(self, underlying: str | None = None) -> list[dict[str, Any]]:
        rows = [json.loads(p) for (p,) in self.db.execute("SELECT payload FROM coverage ORDER BY key")]
        return [r for r in rows if underlying is None or r.get("underlying") == underlying.upper()]

    def covers(self, symbols: Iterable[str], timeframe: str, start: str, end: str, *, slack_days: int = 4) -> list[str]:
        """The symbols whose recorded coverage of `timeframe` bars spans [start, end - slack]
        without a gap longer than `slack_days` (a weekend and a holiday). Start is clamped to
        the first day Alpaca holds any option history."""
        want_start, want_end = _day(max(start[:10], HISTORY_STARTS)), _day(end[:10]) - timedelta(days=slack_days)
        held = []
        for symbol in symbols:
            spans = sorted((_day(r["start"]), _day(r["end"])) for r in self.coverage(symbol)
                           if r.get("timeframe") == timeframe and r.get("status") in ("complete", "current") and r.get("bars"))
            merged: list[list[date]] = []
            for a, b in spans:
                if merged and a <= merged[-1][1] + timedelta(days=slack_days):
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            if any(a <= want_start + timedelta(days=slack_days) and b >= want_end for a, b in merged):
                held.append(symbol.upper())
        return held

    # -- ingestion ---------------------------------------------------------------------------
    def ingest(self, underlyings: Sequence[str], start: str, end: str, *, underlier_bars: Callable[..., list[dict[str, Any]]],
               timeframes: Sequence[str] = ("1Day",), band: float = 0.10, max_days: int = 45, weekly_only: bool = True,
               trades: bool = False, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        """Contracts, then bars (and optionally prints) of the near-the-money contracts of each
        underlying whose life overlaps [start, end]. Every chunk is journaled: an interrupted run
        resumes where it stopped, and a finished one costs nothing to run again.

        Selection: for each expiry E, the contracts whose strike is within `band` of the
        underlying's daily range over [E - max_days, E]. `weekly_only` keeps the last expiry of
        each week (SPY's daily expiries otherwise multiply the download five times); the replay
        chain then omits the others, which the live chain shows."""
        say = progress or (lambda text: None)
        start = max(start[:10], HISTORY_STARTS)
        end = end[:10]
        today = ny_date(self.clock())
        out = []
        for underlying in [u.upper() for u in underlyings]:
            first = (_day(start) - timedelta(days=max_days + 5)).isoformat()
            daily = underlier_bars(underlying, "1Day", first + "T00:00:00Z", end + "T23:59:59Z") or []
            closes = {}
            for bar in daily:
                closes[(datetime.fromtimestamp(_ts(bar["t"]), NY) - timedelta(hours=1)).strftime("%Y-%m-%d")] = bar
            if not closes:
                out.append(self.record_coverage({"underlying": underlying, "timeframe": None, "start": start, "end": end, "status": "unavailable",
                                                 "reason": "no underlying daily bars", "source": SOURCE_CONTRACTS, "bars": 0}))
                continue
            lo = min(float(b["l"]) for b in closes.values()) * (1 - band)
            hi = max(float(b["h"]) for b in closes.values()) * (1 + band)
            expiry_to = (_day(end) + timedelta(days=max_days)).isoformat()
            try:
                self.list_contracts(underlying, start, expiry_to, strike_from=math.floor(lo), strike_to=math.ceil(hi))
            except Exception as exc:  # noqa: BLE001
                out.append(self.record_coverage({"underlying": underlying, "timeframe": None, "start": start, "end": end, "status": "unavailable",
                                                 "reason": f"contract listing refused: {str(exc)[:300]}", "source": SOURCE_CONTRACTS, "bars": 0}))
                continue
            listed = len(self.contracts(underlying, start, expiry_to))
            # The listing row of this window: a later success replaces an earlier refusal.
            self.record_coverage({"underlying": underlying, "timeframe": None, "start": start, "end": end, "status": "complete" if listed else "unavailable",
                                  "reason": "contract listing", "source": SOURCE_CONTRACTS, "contracts": listed, "bars": 0})
            by_expiry: dict[str, list[dict[str, Any]]] = {}
            for row in self.contracts(underlying, start, expiry_to):
                by_expiry.setdefault(row["expiry"], []).append(row)
            expiries = sorted(by_expiry)
            if weekly_only:
                last_of_week: dict[tuple[int, int], str] = {}
                for e in expiries:
                    last_of_week[_day(e).isocalendar()[:2]] = e
                expiries = sorted(set(last_of_week.values()))
            for timeframe in timeframes:
                stats = {"contracts": 0, "with_bars": 0, "bars": 0, "failed_chunks": 0, "expiries": 0}
                asked: list[str] = []
                for expiry in expiries:
                    win_start = max(_day(start), _day(expiry) - timedelta(days=max_days))
                    win_end = min(_day(end), _day(expiry))
                    if win_end < win_start:
                        continue
                    life = [b for d, b in closes.items() if win_start - timedelta(days=4) <= _day(d) <= win_end]
                    if not life:
                        continue
                    low = min(float(b["l"]) for b in life) * (1 - band)
                    high = max(float(b["h"]) for b in life) * (1 + band)
                    chosen = [r["occ"] for r in by_expiry[expiry] if low <= r["strike"] <= high]
                    if not chosen:
                        continue
                    stats["expiries"] += 1
                    stats["contracts"] += len(chosen)
                    asked += chosen
                    key = f"bars:{timeframe}:{underlying}:{expiry}:{win_start}:{win_end}:{band}"
                    if self.done(key):
                        stats["bars"] += int((self.db.execute("SELECT rows FROM chunks WHERE key = ?", (key,)).fetchone() or [0])[0] or 0)
                        continue
                    try:
                        rows = self.fetch_bars(chosen, timeframe, f"{win_start}T00:00:00Z", f"{win_end}T23:59:59Z")
                        if trades:
                            try:
                                self.fetch_trades(chosen, f"{win_start}T00:00:00Z", f"{win_end}T23:59:59Z")
                            except Exception as exc:  # noqa: BLE001 - prints are optional; the refusal is recorded
                                self._mark(f"trades:{underlying}:{expiry}", "failed", 0, str(exc))
                        final = win_end < _day(today)
                        self._mark(key, "done" if final else "partial", rows)
                        stats["bars"] += rows
                        say(f"{underlying} {expiry} {timeframe}: {len(chosen)} contracts, {rows} bars")
                    except Exception as exc:  # noqa: BLE001 - one refused chunk is retried next run
                        stats["failed_chunks"] += 1
                        self._mark(key, "failed", 0, f"{type(exc).__name__}: {exc}")
                        say(f"{underlying} {expiry} {timeframe}: FAILED {str(exc)[:120]}")
                # What THIS window holds (found in review: counting every stored bar of the
                # underlying let a refresh whose every chunk failed still read as coverage).
                for i in range(0, len(asked), 500):
                    group = asked[i:i + 500]
                    stats["with_bars"] += int(self.db.execute(
                        f"SELECT COUNT(DISTINCT occ) FROM bars WHERE timeframe = ? AND t >= ? AND t <= ? AND occ IN ({','.join('?' * len(group))})",
                        (timeframe, f"{start}T00:00:00Z", f"{(_day(end) + timedelta(days=1)).isoformat()}T23:59:59Z", *group)).fetchone()[0])
                # `complete`: every chunk in, the window closed. `current`: every chunk in, the
                # window reaches today (refetched next time). `partial`: a chunk failed, so this
                # window is NOT coverage. `unavailable`: nothing printed or nothing came back.
                status = ("unavailable" if not stats["bars"] else "partial" if stats["failed_chunks"]
                          else "current" if _day(end) >= _day(today) else "complete")
                out.append(self.record_coverage({
                    "underlying": underlying, "timeframe": timeframe, "start": start, "end": end, "status": status,
                    "source": SOURCE_BARS, "listing": SOURCE_CONTRACTS, "band": band, "max_days": max_days, "weekly_only": weekly_only,
                    **stats,
                    "trades": ("requested: see chunks for refusals" if trades else "not requested"),
                    "quotes": "unavailable: Alpaca has no historical option quotes; replay quotes are estimated from prints",
                    "not_point_in_time": ["open_interest", "close_price", "greeks"],
                    "point_in_time_listing": "a contract exists from its first print (no listing date is published)",
                }))
        return out

    # -- features for the equity and ETF desks -------------------------------------------------
    def features_for_day(self, symbol: str, day: str, spot: float, *, target_days: int = 30) -> dict[str, Any] | None:
        """IV, 25-delta skew and activity of one underlying from the day's OPRA closing prints.

        COMPUTED here: implied volatility (Black-Scholes, RISK_FREE and DIVIDEND_YIELD assumed)
        from each contract's daily close against the underlying's daily close; deltas from those
        IVs; `atm_iv` (call and put nearest the money of the expiry nearest `target_days`);
        `put_25d_iv`, `call_25d_iv` and `skew_25d` (put minus call) at the contracts whose
        computed delta is nearest -0.25 and +0.25. GIVEN by the venue: volume and trade counts,
        summed over the ingested band only (not the whole chain). NOT AVAILABLE: vendor greeks,
        point-in-time open interest, and the direction of any trade. Caveat: an option's close is
        its LAST print, which can be hours before the underlying's close; contracts with fewer
        than 5 prints that day are left out of the IV fields."""
        symbol = symbol.upper()
        stamp = close_stamp(f"{day}T12:00:00Z", "1Day")  # available at the NY midnight after the session
        at_ts = datetime.combine(_day(day), datetime.min.time(), NY).replace(hour=16).timestamp()
        cur = self.db.execute("SELECT c.occ, c.expiry, c.strike, c.right, b.c, b.v, b.n FROM bars b JOIN contracts c ON c.occ = b.occ "
                              "WHERE c.underlying = ? AND b.timeframe = '1Day' AND b.t = ? AND c.expiry > ?", (symbol, stamp, day))
        rows = [dict(zip(("occ", "expiry", "strike", "right", "c", "v", "n"), r)) for r in cur]
        if not rows or not spot or spot <= 0:
            return None
        volume = {"call": sum(r["v"] for r in rows if r["right"] == "call"), "put": sum(r["v"] for r in rows if r["right"] == "put")}
        trades = sum(int(r["n"] or 0) for r in rows)
        out: dict[str, Any] = {
            "t": stamp, "day": day, "underlying_close": spot, "contracts_printed": len(rows),
            "option_volume": volume["call"] + volume["put"], "call_volume": volume["call"], "put_volume": volume["put"],
            "put_call_volume_ratio": round(volume["put"] / volume["call"], 4) if volume["call"] > 0 else None,
            "option_trades": trades, "atm_iv": None, "put_25d_iv": None, "call_25d_iv": None, "skew_25d": None, "expiry_used": None, "days_to_expiry": None,
            "version": FEATURE_VERSION,
            "computed": ["atm_iv", "put_25d_iv", "call_25d_iv", "skew_25d", "deltas"],
            "given": ["option_volume", "call_volume", "put_volume", "option_trades"],
            "assumed": {"risk_free": RISK_FREE, "dividend_yield": DIVIDEND_YIELD, "model": "European Black-Scholes on American contracts"},
            "not_available": ["vendor greeks", "point-in-time open interest", "trade direction"],
            "source": SOURCE_BARS,
        }
        liquid = [r for r in rows if int(r["n"] or 0) >= 5]
        by_expiry: dict[str, list[dict[str, Any]]] = {}
        for r in liquid:
            days = (_day(r["expiry"]) - _day(day)).days
            if 5 <= days <= 60:
                by_expiry.setdefault(r["expiry"], []).append(r)
        if not by_expiry:
            return out
        expiry = min(by_expiry, key=lambda e: (abs((_day(e) - _day(day)).days - target_days), e))
        years = years_to(expiry, at_ts)
        solved = []
        for r in by_expiry[expiry]:
            vol = implied_vol(float(r["c"]), spot, float(r["strike"]), years, r["right"])
            if vol is not None:
                solved.append({**r, "iv": vol, "delta": bs_delta(spot, float(r["strike"]), years, vol, r["right"])})
        calls = [r for r in solved if r["right"] == "call"]
        puts = [r for r in solved if r["right"] == "put"]
        if not calls or not puts:
            return out
        near = lambda rows: min(rows, key=lambda r: abs(r["strike"] - spot))  # noqa: E731
        out.update(expiry_used=expiry, days_to_expiry=(_day(expiry) - _day(day)).days, atm_iv=round((near(calls)["iv"] + near(puts)["iv"]) / 2, 6))
        put25 = min(puts, key=lambda r: abs(r["delta"] + 0.25))
        call25 = min(calls, key=lambda r: abs(r["delta"] - 0.25))
        if abs(put25["delta"] + 0.25) <= 0.12 and abs(call25["delta"] - 0.25) <= 0.12:
            out.update(put_25d_iv=round(put25["iv"], 6), call_25d_iv=round(call25["iv"], 6), skew_25d=round(put25["iv"] - call25["iv"], 6),
                       put_25d_delta=round(put25["delta"], 4), call_25d_delta=round(call25["delta"], 4))
        return out

    def compute_features(self, symbol: str, closes: Mapping[str, float]) -> int:
        """Compute and keep the feature row of every day in `closes` (NY date -> underlying close)
        that has none yet. Live and replay both read these rows, so they see the same number."""
        made = 0
        for day, spot in sorted(closes.items()):
            if self.db.execute("SELECT 1 FROM features WHERE symbol = ? AND day = ? AND version = ?", (symbol.upper(), day, FEATURE_VERSION)).fetchone():
                continue
            row = self.features_for_day(symbol, day, float(spot))
            if row is None:
                continue
            with self._lock:
                self.db.execute("INSERT OR REPLACE INTO features VALUES (?, ?, ?, ?, ?)", (symbol.upper(), day, FEATURE_VERSION, row["t"], json.dumps(row, sort_keys=True)))
                self.db.commit()
            made += 1
        return made

    def feature_series(self, symbols: Sequence[str], start: str = "", end: str = "9999") -> dict[str, list[dict[str, Any]]]:
        """Stored feature rows by symbol, oldest first, stamped with when each became available."""
        out: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            cur = self.db.execute("SELECT payload FROM features WHERE symbol = ? AND version = ? AND available_at >= ? AND available_at <= ? ORDER BY available_at",
                                  (symbol.upper(), FEATURE_VERSION, start, end))
            rows = [json.loads(p) for (p,) in cur]
            if rows:
                out[symbol.upper()] = rows
        return out

    def features_at(self, symbols: Sequence[str], now_ts: float) -> dict[str, Any]:
        """The latest feature row of each symbol available at `now_ts` (what a live wake sees)."""
        out = {}
        for symbol in symbols:
            row = self.db.execute("SELECT payload FROM features WHERE symbol = ? AND version = ? AND available_at <= ? ORDER BY available_at DESC LIMIT 1",
                                  (symbol.upper(), FEATURE_VERSION, iso(now_ts))).fetchone()
            if row:
                out[symbol.upper()] = json.loads(row[0])
        return out

    # -- the options desk's replay tape ------------------------------------------------------------
    def tape(self, needs: Mapping[str, Any], start: str, end: str, *, horizon: str, underlier_bars: Callable[..., list[dict[str, Any]]],
             warmup: int = 70, execution: str = "15Min", max_order_usd: float = 75.0, spread: Mapping[str, Any] | None = None,
             liquidity: Mapping[str, Any] | None = None, fee_per_contract: float = FEE_PER_CONTRACT_USD,
             max_option_bars: int | None = None) -> dict[str, Any]:
        """A replay tape for an options strategy (`league/options_replay.py` walks it).

        Steps are the regular-session closes of the underlyings' `execution` bars. A step carries
        the underlyings' bars (`execution_bars`), the signal bars that became available by then
        (`history_bars`), and the option bars that closed at it (`options`). `contracts` says
        when each contract first printed, which is when the replay may show it.

        A STRUCTURE agent's tape (NEEDS `"structures": true`, Sept 25, 2026) carries what its live chain
        can show (`House._chain(structures=True)`): no single-contract affordability line (a leg is not
        bought alone), 0 to `max_days_to_expiry` days (7 when unstated), and only bars whose strike is
        within the chain's 20% of the underlying's last close then (`STRUCTURE_BAND`), which bounds a
        month of SPY, QQQ and IWM 0-7 day contracts to about 80,000, 75,000 and 25,000 bars (measured on
        the local copy, Sept 25, 2026). A structure tape is also held to `STRUCTURE_TAPE_MAX_BARS` option
        bars (`max_option_bars`): over it, the OLDEST steps are dropped (their signal bars joining the
        warmup) and the tape says so under `bounded`."""
        symbols = [str(s).upper() for s in (needs.get("symbols") or [])][:8]
        structural = bool(needs.get("structures"))
        asked = needs.get("max_days_to_expiry")
        # A structure agent's 0 is a 0-DTE strategy's own answer, not "unsaid" (`House._structure_context`).
        days = (max(0, min(int(7 if asked is None else asked), 45)) if structural
                else max(2, min(int(asked or 21), 45)))
        timeframe = str((needs.get("bars") or {}).get("timeframe") or "1Day")
        afford = float("inf") if structural else float(max_order_usd) / MULTIPLIER
        start_ts, end_ts = _ts(start), _ts(end)
        warm_reach = warmup * (1.6 if timeframe == "1Day" else 1.0) * TIMEFRAMES.get(timeframe, 86400) + 7 * 86400
        signals, warmup_bars, execution_rows = {}, {}, {}
        for symbol in symbols:
            rows = underlier_bars(symbol, timeframe, iso(start_ts - warm_reach), end) or []
            warmup_bars[symbol] = [b for b in rows if _ts(b["t"]) < start_ts][-warmup:]
            signals[symbol] = [b for b in rows if _ts(b["t"]) >= start_ts]
            execution_rows[symbol] = [b for b in (underlier_bars(symbol, execution, start, end) or []) if _in_session(_ts(b["t"]))]
        contracts: dict[str, dict[str, Any]] = {}
        live = {**LIQUIDITY, **dict(liquidity or {})}
        by_time: dict[str, dict[str, Any]] = {}
        for symbol, rows in execution_rows.items():
            for bar in rows:
                by_time.setdefault(bar["t"], {"execution_bars": {}, "options": {}})["execution_bars"][symbol] = {k: bar[k] for k in ("o", "h", "l", "c", "v")}
        first_day, last_day = ny_date(start_ts), (_day(ny_date(end_ts)) + timedelta(days=days)).isoformat()
        closes: dict[str, list[tuple[str, float]]] = {s: sorted((t, float(v["execution_bars"][s]["c"])) for t, v in by_time.items()
                                                              if s in v["execution_bars"]) for s in symbols}
        for symbol in symbols:
            listed = {r["occ"]: r for r in self.contracts(symbol, first_day, last_day)}
            stamps = [t for t, _ in closes.get(symbol, [])]
            prices = [c for _, c in closes.get(symbol, [])]

            def near(t: str, strike: float) -> bool:
                """A structure tape keeps a bar only where the chain could show its contract: within
                STRUCTURE_BAND of the underlying's last close at or before it (kept when none is known)."""
                index = bisect.bisect_right(stamps, t) - 1
                return index < 0 or abs(strike / prices[index] - 1.0) <= STRUCTURE_BAND
            names = list(listed)
            for i in range(0, len(names), 500):
                group = names[i:i + 500]
                marks = ",".join("?" * len(group))
                window = (execution, iso(start_ts), end, *group)
                # When each first printed in the window (any bar at all is evidence it existed).
                first = dict(self.db.execute(f"SELECT occ, MIN(t) FROM bars WHERE timeframe = ? AND t >= ? AND t <= ? AND occ IN ({marks}) GROUP BY occ", window))
                # Only bars that can quote or fill ride on the tape (46% of the 15-minute bars
                # cannot, Sept 22, 2026), as compact rows, read one contract at a time.
                cur = self.db.execute(f"SELECT occ, t, o, h, l, c, v, n FROM bars WHERE timeframe = ? AND t >= ? AND t <= ? AND occ IN ({marks}) "
                                      "AND v >= ? AND n >= ? ORDER BY occ, t", (*window, float(live["min_volume"]), int(live["min_trades"])))
                current, kept = None, []

                def flush(occ: str | None, rows: list[tuple]) -> None:
                    # A superset of what any step could show: it printed, at some qualifying print
                    # its premium was within one order, and it was inside its last `days` (plus
                    # four for the spread estimate). A held contract was affordable when bought.
                    if occ is None or not rows or min(r[4] for r in rows) > afford:
                        return
                    row = listed[occ]
                    contracts[occ] = {"underlying": symbol, "expiry": row["expiry"], "strike": row["strike"], "right": row["right"],
                                      "first_print": first.get(occ) or rows[0][0]}
                    for t, o, h, l, c, v, n in rows:
                        step = by_time.get(t)
                        if step is None and _in_session(_ts(t)):
                            step = by_time.setdefault(t, {"execution_bars": {}, "options": {}})
                        if step is not None:
                            step["options"][occ] = [o, h, l, c, v, n]  # compact: o h l c v n

                shown_from = ""
                for occ, t, o, h, l, c, v, n in cur:
                    if occ != current:
                        flush(current, kept)
                        current, kept = occ, []
                        shown_from = iso(datetime.combine(_day(listed[occ]["expiry"]) - timedelta(days=days + 4), datetime.min.time(), NY).timestamp())
                    if t >= shown_from and (not structural or near(t, float(listed[occ]["strike"]))):
                        kept.append((t, o, h, l, c, v, int(n or 0)))
                flush(current, kept)
        # Recorded OPRA quotes (from Sept 22, 2026, when the House began keeping them): the last
        # one of each contract in (previous step, step] rides on the step; nothing is carried.
        # Streamed from the store onto the steps (never held as one list: a structure tape's
        # contracts have up to hundreds of thousands of them, and the local copy is read on a laptop).
        times = sorted(by_time)
        recorded = 0
        names = list(contracts)
        for i in range(0, len(names), 500):
            group = names[i:i + 500]
            marks = ",".join("?" * len(group))
            for occ, t, bid, ask in self.db.execute(f"SELECT occ, t, bid, ask FROM quotes WHERE t >= ? AND t <= ? AND occ IN ({marks}) ORDER BY occ, t",
                                                    (iso(start_ts), end, *group)):
                recorded += 1
                index = bisect.bisect_left(times, t)  # the first step at or after the quote
                if index < len(times):
                    by_time[times[index]].setdefault("quotes", {})[occ] = {"t": t, "bid": bid, "ask": ask}
        steps = []
        cursors = {s: 0 for s in symbols}
        for t in sorted(by_time):
            entry = {"t": t, "bars": {}, **by_time[t]}
            for symbol in symbols:
                rows, index = signals.get(symbol, []), cursors[symbol]
                while index < len(rows) and rows[index]["t"] <= t:
                    entry.setdefault("history_bars", {}).setdefault(symbol, []).append(rows[index])
                    index += 1
                cursors[symbol] = index
            steps.append(entry)
        bounded = None
        cap = STRUCTURE_TAPE_MAX_BARS if max_option_bars is None else int(max_option_bars)
        total = sum(len(entry["options"]) for entry in steps)
        if structural and total > cap:
            first, kept = 0, total
            while first < len(steps) and kept > cap:
                kept -= len(steps[first]["options"])
                first += 1
            for entry in steps[:first]:  # the dropped steps' signal bars are the kept steps' warmup
                for symbol, rows in (entry.get("history_bars") or {}).items():
                    warmup_bars.setdefault(symbol, []).extend(rows)
            warmup_bars = {symbol: rows[-warmup:] for symbol, rows in warmup_bars.items()}
            steps = steps[first:]
            printed = {occ for entry in steps for occ in entry["options"]} | {occ for entry in steps for occ in entry.get("quotes") or {}}
            contracts = {occ: row for occ, row in contracts.items() if occ in printed}
            bounded = {"option_bars": total, "kept": kept, "max_option_bars": cap, "from": steps[0]["t"] if steps else None,
                       "why": "a structure tape is held to what a box replays well inside its time and memory"}
        coverage = {s: [r for r in self.coverage(s) if r.get("timeframe") == execution] for s in symbols}
        return {
            "venue": "alpaca", "asset_class": "option", "horizon": horizon, "timeframe": timeframe, "execution_timeframe": execution,
            "step_seconds": TIMEFRAMES[execution], "symbols": symbols, "warmup_bars": warmup_bars, "warmup_requested": warmup,
            "half_spread_bps": 1.0, "steps": steps, "contracts": contracts,
            "chain_rules": ({"max_days_to_expiry": days, "moneyness": 0.20, "per_underlying": 80, "afford_per_share": None, "structures": True}
                            if structural else {"max_days_to_expiry": days, "moneyness": 0.20, "per_underlying": 40, "afford_per_share": afford}),
            "spread_model": {**SPREAD_MODEL, **dict(spread or {})}, "liquidity": live,
            "fee_per_contract_usd": float(fee_per_contract), "multiplier": MULTIPLIER,
            "recorded_quotes": recorded,
            "provenance": {"options": SOURCE_BARS, "listing": SOURCE_CONTRACTS, "quotes": SPREAD_MODEL["kind"],
                           "recorded_quotes": "OPRA quotes the House read for live chains, where they exist (Sept 22, 2026 on)",
                           "underlying": "the House's underlier bars adapter", "history_starts": HISTORY_STARTS},
            "coverage": {s: [{k: r.get(k) for k in ("status", "start", "end", "contracts", "with_bars", "bars")} for r in rows] for s, rows in coverage.items()},
            # What a live wake of these NEEDS is handed besides (`House.snapshot`), stamped with when each
            # row became available: the options-derived features it declares (Sept 25, 2026).
            **({"options_features": self.feature_series(symbols)} if needs.get("options_features") else {}),
            **({"bounded": bounded} if bounded else {}),
            **({"structure_hours": structure_hours(first_day, last_day)} if structural else {}),
        }


def structure_hours(first: str, last: str) -> dict[str, list[int]]:
    """{day: [entry cut, House close]} in New York minutes for the days in [first, last] whose structure
    hours are not the regular 14:30 and 15:30: an early close (13:00 the day after Thanksgiving and on
    Christmas Eve) holds them 90 and 30 minutes before the bell, as `House._structure_hours` does. Read
    from the House's session calendar (`ltcm.data`) where the tape is built; the replay in the box
    reads them off the tape. Empty where the calendar cannot be read (the regular hours then)."""
    try:
        from ltcm.data import to_datetime, us_equity_session
    except ImportError:
        return {}
    out: dict[str, list[int]] = {}
    day, end = _day(first), _day(last)
    while day <= end:
        try:
            session = us_equity_session(day.isoformat())
        except Exception:  # noqa: BLE001 - a day outside the calendar keeps the regular hours
            session = None
        if session is not None:
            bell = to_datetime(session.close_at).astimezone(NY)
            minutes = bell.hour * 60 + bell.minute
            hours = [min(14 * 60 + 30, minutes - 90), min(15 * 60 + 30, minutes - 30)]
            if hours != [14 * 60 + 30, 15 * 60 + 30]:
                out[day.isoformat()] = hours
        day += timedelta(days=1)
    return out


def _in_session(ts: float) -> bool:
    """A bar CLOSING inside 09:30 (exclusive) to 16:00 New York on a weekday: the regular session
    the House trades options in. (SPY, QQQ and IWM options trade until 16:15; a day order does
    not, and the House's wakes after 16:00 see a shut market.)"""
    moment = datetime.fromtimestamp(ts, NY)
    minutes = moment.hour * 60 + moment.minute
    return moment.weekday() < 5 and 570 < minutes <= 960


def daily_closes(bars: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Close-stamped daily bars as {NY session date: close}."""
    return {(datetime.fromtimestamp(_ts(b["t"]), NY) - timedelta(hours=1)).strftime("%Y-%m-%d"): float(b["c"]) for b in bars}


def adapter_from(alpaca_data: Any) -> Callable[[str, str, str, str], list[dict[str, Any]]]:
    """`underlier_bars(symbol, timeframe, start, end)`: closed, close-stamped stock bars through
    the House's `AlpacaData` client (the history store can back the same signature later).

    UNADJUSTED prices (`adjustment=raw`). Strikes and premiums are never adjusted, and Alpaca's
    `adjustment=all` history is adjusted for dividends and splits that came AFTER each bar: a
    small lookahead against every strike, and a broken moneyness filter across a split (found
    in review, Sept 22, 2026). The same spot feeds the tape, the chain filter and the IVs."""
    from .tapes import PAGE_LIMIT as STOCK_PAGE, STOCK_BARS_PATH, TIMEFRAME_SECONDS, iso as stamp, parse_time

    def underlier_bars(symbol: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        seconds, name = TIMEFRAME_SECONDS[timeframe], symbol.upper()
        start_ts, end_ts = parse_time(start), min(parse_time(end), float(alpaca_data.clock()))
        found: dict[int, dict[str, Any]] = {}
        token = None
        for _ in range(int(getattr(alpaca_data, "max_pages", 60))):
            params = {"symbols": name, "timeframe": timeframe, "start": stamp(start_ts - seconds), "end": stamp(end_ts),
                      "limit": STOCK_PAGE, "feed": alpaca_data.feed, "adjustment": "raw", "page_token": token}
            url = alpaca_data.url(STOCK_BARS_PATH, params)
            payload = _retrying(lambda url=url: alpaca_data._get(url, what="alpaca stock bars (unadjusted)"))
            for row in (payload.get("bars") or {}).get(name) or []:
                bar = alpaca_data._bar(row, seconds, daily_equity=timeframe == "1Day")
                if bar is not None and start_ts <= bar[0] <= end_ts:
                    found[int(bar[0])] = bar[1]
            token = payload.get("next_page_token")
            if not token:
                break
        return [found[key] for key in sorted(found)]
    return underlier_bars


#: The calibration's buckets (`fit_spread_calibration`): premium bands of the last print, and at $3 and
#: over a moneyness band too; the index ETFs' $0.5-3 legs are one band (one day of their quotes, Sept 23).
SPREAD_BUCKETS = (
    {"class": "etf", "premium": [0.0, 0.5], "moneyness": None},
    {"class": "etf", "premium": [0.5, 3.0], "moneyness": None},
    {"class": "etf", "premium": [3.0, None], "moneyness": [0.0, 0.03]},
    {"class": "etf", "premium": [3.0, None], "moneyness": [0.03, None]},
    {"class": "stock", "premium": [0.0, 0.5], "moneyness": None},
    {"class": "stock", "premium": [0.5, 1.0], "moneyness": None},
    {"class": "stock", "premium": [1.0, 3.0], "moneyness": None},
    {"class": "stock", "premium": [3.0, None], "moneyness": [0.0, 0.03]},
    {"class": "stock", "premium": [3.0, None], "moneyness": [0.03, None]},
)


#: The fill half-spread table fitted on the House's recorded OPRA quotes (`fit_spread_calibration` over
#: the local copy, Sept 25, 2026, builder S3): 316,141 quotes of Sept 22 14:55Z - Sept 24 20:00Z, 11,111
#: of them within 300 s of a qualifying bar of their contract (the index ETFs' only on Sept 23: their
#: 15-minute bars of Sept 24 were not yet stored, and their Mon-Thu expiries have none), the 97.5th
#: percentile of the one-sided distance from the last print to the real touch, a cent at least.
#: On those quotes it is tighter than the real ask 5.6% / bid 7.6% of the time for the ETFs (the current
#: estimate: 6.6% / 9.3%) and 2.3% / 1.3% for single stocks (the current estimate: 27.2% / 25.4%);
#: held out (the same fit on Sept 22-23 only, judged on Sept 24's 4,557 single-stock quotes) 9.7% / 6.6%,
#: a median $0.09 short (current: 30.6% / 28.2%, $0.024). OFF unless a tape's `spread_model["calibration"]` names it (`scripts/replay_structures.py
#: --calibrated`); refit it (`python -m league.options_history calibrate`) as the House records more.
CALIBRATED_SPREADS = {
    "version": "opra-quotes-2026-09-22..24-q0.975-gap300s", "quantile": 0.975, "max_gap_seconds": 300.0, "min_quotes": 60,
    "etf": ["IWM", "QQQ", "SPY"],
    "buckets": [
        {"class": "etf", "premium": [0.0, 0.5], "moneyness": None, "half": 0.02, "quotes": 108},
        {"class": "etf", "premium": [0.5, 3.0], "moneyness": None, "half": 0.07, "quotes": 99},
        {"class": "etf", "premium": [3.0, None], "moneyness": [0.0, 0.03], "half": 0.25, "quotes": 66},
        {"class": "etf", "premium": [3.0, None], "moneyness": [0.03, None], "half": 2.79, "quotes": 29},
        {"class": "stock", "premium": [0.0, 0.5], "moneyness": None, "half": 0.06, "quotes": 6437},
        {"class": "stock", "premium": [0.5, 1.0], "moneyness": None, "half": 0.14, "quotes": 1612},
        {"class": "stock", "premium": [1.0, 3.0], "moneyness": None, "half": 0.46, "quotes": 1499},
        {"class": "stock", "premium": [3.0, None], "moneyness": [0.0, 0.03], "half": 1.02, "quotes": 622},
        {"class": "stock", "premium": [3.0, None], "moneyness": [0.03, None], "half": 1.86, "quotes": 639},
    ],
}


def _quantile(values: Sequence[float], p: float) -> float | None:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))] if ordered else None


def fit_spread_calibration(store: OptionsHistory, underlier_bars: Callable[..., list[dict[str, Any]]], *, quantile: float = 0.975,
                           max_gap: float = 300.0, min_quotes: int = 60, etf: Sequence[str] = ("SPY", "QQQ", "IWM"),
                           start: str = "", end: str = "9999", liquidity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A fill half-spread table fitted on the recorded OPRA quotes (`SPREAD_MODEL["calibration"]`).

    The replay prices a fill around a leg's LAST PRINT c in a 15-minute bar; it cannot know the mid. So
    what a fill half-spread h must cover is not the quoted half-spread but the distance from c to the
    real touch the fill trades at: a buy is flattered when c + h < the ask, a sell when c - h > the bid.
    Each recorded quote is paired with its contract's last qualifying bar (the tape's `min_volume` and
    `min_trades`) closed at most `max_gap` seconds before it -- a fill-time pairing: the replay fills at
    that bar's close -- and each bucket's h is the `quantile` of the larger one-sided need (ask - c,
    c - bid), never under a cent. Buckets measured on fewer than `min_quotes` keep the estimate.

    `check` says, on the same quotes, how often the table and the current estimate are tighter than
    the real touch (buy and sell), and by how much. The table is only as good as the days it saw: refit
    it as the House records more (a Friday's 0-DTE legs, the daily expiries)."""
    live = {**LIQUIDITY, **dict(liquidity or {})}
    etf_set = {str(x).upper() for x in etf}
    quotes: dict[str, list[tuple[str, float, float]]] = {}
    for occ, t, bid, ask in store.db.execute("SELECT occ, t, bid, ask FROM quotes WHERE t >= ? AND t <= ? ORDER BY occ, t", (start, end)):
        quotes.setdefault(occ, []).append((t, float(bid), float(ask)))
    total = sum(len(rows) for rows in quotes.values())
    if not quotes:
        raise HistoryError("no recorded quotes to calibrate on")
    first = min(rows[0][0] for rows in quotes.values())
    last_t = max(rows[-1][0] for rows in quotes.values())
    bars_from = iso(_ts(first) - 7 * 86400)
    spots: dict[str, tuple[list[float], list[float]]] = {}
    for root in sorted({occ[:-15] for occ in quotes}):
        rows = underlier_bars(root, "15Min", bars_from, last_t) or []
        spots[root] = ([_ts(r["t"]) for r in rows], [float(r["c"]) for r in rows])
    pairs = []
    names = list(quotes)
    for i in range(0, len(names), 400):
        group = names[i:i + 400]
        marks = ",".join("?" * len(group))
        printed: dict[str, list[tuple]] = {}
        for occ, t, h, l, c in store.db.execute(
                f"SELECT occ, t, h, l, c FROM bars WHERE timeframe = '15Min' AND t >= ? AND t <= ? AND v >= ? AND n >= ? AND occ IN ({marks}) ORDER BY occ, t",
                (bars_from, last_t, float(live["min_volume"]), int(live["min_trades"]), *group)):
            printed.setdefault(occ, []).append((_ts(t), float(h), float(l), float(c)))
        for occ in group:
            mine = printed.get(occ)
            if not mine:
                continue
            stamps = [b[0] for b in mine]
            parsed = parse_occ(occ)
            root = parsed["underlying"]
            for t, bid, ask in quotes[occ]:
                at = _ts(t)
                k = bisect.bisect_right(stamps, at) - 1
                if k < 0 or at - stamps[k] > max_gap:
                    continue
                times, closes = spots.get(root, ([], []))
                j = bisect.bisect_right(times, at) - 1
                ranges = [max(0.0, b[1] - b[2]) for b in mine[max(0, k - int(SPREAD_MODEL["range_bars"])):k]]
                current = estimate_quote({"c": mine[k][3]}, ranges)[2]
                pairs.append({"root": root, "c": mine[k][3], "strike": parsed["strike"], "spot": closes[j] if j >= 0 else None,
                              "bid": bid, "ask": ask, "day": t[:10], "current": current})
    calibration = {"version": f"opra-quotes-q{quantile}-gap{int(max_gap)}s", "quantile": quantile, "max_gap_seconds": max_gap,
                   "min_quotes": min_quotes, "etf": sorted(etf_set), "buckets": []}
    members: dict[int, list[dict[str, Any]]] = {}
    for pair in pairs:
        row = spread_bucket({"etf": sorted(etf_set), "buckets": [dict(b, index=n) for n, b in enumerate(SPREAD_BUCKETS)]},
                            pair["root"], pair["c"], pair["strike"], pair["spot"])
        if row is not None:
            members.setdefault(row["index"], []).append(pair)
    for n, bucket in enumerate(SPREAD_BUCKETS):
        group = members.get(n) or []
        need = max(_quantile([p["ask"] - p["c"] for p in group], quantile) or 0.0, _quantile([p["c"] - p["bid"] for p in group], quantile) or 0.0)
        calibration["buckets"].append({**bucket, "half": round(max(0.01, need), 4), "quotes": len(group),
                                       "quoted_half_median": _quantile([(p["ask"] - p["bid"]) / 2 for p in group], 0.5)})

    def tighter(half_of: Callable[[dict[str, Any]], float]) -> dict[str, Any]:
        out = {}
        for kind in ("etf", "stock"):
            group = [p for p in pairs if (p["root"] in etf_set) == (kind == "etf")]
            if not group:
                continue
            halves = [half_of(p) for p in group]
            short = [x for p, h in zip(group, halves) for x in (p["ask"] - (p["c"] + h), (p["c"] - h) - p["bid"]) if x > 1e-9]
            out[kind] = {"quotes": len(group), "median_half": _quantile(halves, 0.5),
                         "buy_tighter": round(sum(1 for p, h in zip(group, halves) if p["c"] + h < p["ask"] - 1e-9) / len(group), 4),
                         "sell_tighter": round(sum(1 for p, h in zip(group, halves) if p["c"] - h > p["bid"] + 1e-9) / len(group), 4),
                         "median_shortfall": _quantile(short, 0.5) or 0.0}
        return out

    def table_half(pair: dict[str, Any]) -> float:
        measured = calibrated_half(calibration, pair["root"], pair["c"], pair["strike"], pair["spot"])
        return pair["current"] if measured is None else max(tick(pair["c"]), measured)

    calibration["fitted_on"] = {"from": first, "to": last_t, "days": sorted({p["day"] for p in pairs}), "quotes_recorded": total,
                                "quotes_paired": len(pairs)}
    calibration["check"] = {"calibrated": tighter(table_half), "current": tighter(lambda p: p["current"])}
    return calibration


def stored_underlier(store: OptionsHistory) -> Callable[[str, str, str, str], list[dict[str, Any]]]:
    """`underlier_bars(symbol, timeframe, start, end)` read from the store's `underlier_bars` table
    instead of the gateway: the same close-stamped, UNADJUSTED bars `adapter_from` returns, as
    `adapter_from` fetched them when the copy was made (a bar whose close is in [start, end]).

    The table is not part of `SCHEMA`: only a LOCAL copy of the store carries it (Sept 25, 2026, the
    options-desk run: `~/Work/.options-history/`, made on the House box with the House's own data
    client, so a structure replay on a laptop needs no gateway and never touches the box)."""
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'underlier_bars'").fetchone():
        raise HistoryError(f"{store.path} holds no underlier bars: only a local copy of the store does")

    def underlier_bars(symbol: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        rows = store.db.execute("SELECT payload FROM underlier_bars WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                                (symbol.upper(), timeframe, _ts(start), _ts(end)))
        return [json.loads(payload) for (payload,) in rows]
    return underlier_bars


def refresh(store: OptionsHistory, symbols: Sequence[str], underlier_bars: Callable[..., list[dict[str, Any]]], *,
            days: int = 10, timeframes: Sequence[str] = ("1Day",), band: float = 0.10, max_days: int = 45) -> dict[str, Any]:
    """The House's daily job: the last `days` of bars for `symbols`, then their feature rows.
    The options desk's refresh must use the band of its backfill (0.2, the chain's own 20%),
    or the recent part of a tape would show fewer contracts than the older part."""
    end = ny_date(store.clock())
    start = (_day(end) - timedelta(days=days)).isoformat()
    coverage = store.ingest(symbols, start, end, underlier_bars=underlier_bars, timeframes=timeframes, band=band, max_days=max_days)
    made = {}
    for symbol in symbols:
        daily = underlier_bars(symbol, "1Day", f"{start}T00:00:00Z", f"{end}T23:59:59Z")
        made[symbol] = store.compute_features(symbol, daily_closes(daily))
    return {"coverage": [{k: r.get(k) for k in ("underlying", "timeframe", "status", "bars")} for r in coverage], "features": made}


def main(argv: list[str] | None = None) -> int:
    """`python -m league.options_history ingest --symbols SPY,QQQ --start 2026-05-01 --end 2026-09-18`."""
    parser = argparse.ArgumentParser(description="Ingest listed-option history through the gateway (market-data GETs only).")
    parser.add_argument("command", choices=("ingest", "coverage", "features", "calibrate"))
    parser.add_argument("--quantile", type=float, default=0.975)
    parser.add_argument("--max-gap", type=float, default=300.0)
    parser.add_argument("--store", default="/workspace/state/options_history.sqlite")
    parser.add_argument("--symbols", default="SPY,QQQ")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--timeframes", default="1Day")
    parser.add_argument("--band", type=float, default=0.10)
    parser.add_argument("--max-days", type=int, default=45)
    parser.add_argument("--all-expiries", action="store_true")
    parser.add_argument("--trades", action="store_true")
    parser.add_argument("--env", default="")
    args = parser.parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.command == "coverage":
        print(json.dumps(OptionsHistory(args.store).coverage(), indent=1))
        return 0
    if args.command == "calibrate":
        store = OptionsHistory(args.store)
        try:
            underlier = stored_underlier(store)  # a local copy carries its underlying bars
        except HistoryError:
            underlier = None
        if underlier is not None:
            print(json.dumps(fit_spread_calibration(store, underlier, quantile=args.quantile, max_gap=args.max_gap), indent=1))
            return 0
    from .service import load_config, load_env, secret
    from .tapes import AlpacaData
    from .venues import gateway_broker
    if args.env:
        load_env(Path(args.env))
    config = load_config()
    broker = gateway_broker("alpaca-paper", gateway_url=config["gateway_url"], token=secret("GATEWAY_TOKEN"),
                            feed=config.get("alpaca_feed", "iex"), option_feed=config.get("alpaca_option_feed", "indicative"))
    data = AlpacaData(broker.client, feed=config.get("alpaca_feed", "iex"))
    underlier = adapter_from(data)
    store = OptionsHistory(args.store, gateway_get(broker))
    if args.command == "calibrate":  # the House's store: its underlying bars through the gateway (market-data GETs)
        print(json.dumps(fit_spread_calibration(store, underlier, quantile=args.quantile, max_gap=args.max_gap), indent=1))
        return 0
    if args.command == "ingest":
        rows = store.ingest(symbols, args.start, args.end or ny_date(time.time()), underlier_bars=underlier,
                            timeframes=[t for t in args.timeframes.split(",") if t], band=args.band, max_days=args.max_days,
                            weekly_only=not args.all_expiries, trades=args.trades, progress=lambda text: print(text, flush=True))
        print(json.dumps(rows, indent=1))
    for symbol in symbols:
        daily = underlier(symbol, "1Day", (args.start or HISTORY_STARTS) + "T00:00:00Z", (args.end or ny_date(time.time())) + "T23:59:59Z")
        print(symbol, "feature rows made:", store.compute_features(symbol, daily_closes(daily)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Sequence
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
}
#: A structure tape keeps a contract's bar only within this fraction of the underlying's price then:
#: the chain's own moneyness line (`House._chain`), so nothing a structure agent could be shown is lost.
STRUCTURE_BAND = 0.20
#: The most option bars a structure tape carries. Measured Sept 25, 2026 on the local copy: SPY, QQQ and IWM at 0-7 days over
#: the House's whole options window (May 16 to Sept 24, 2,340 steps) are 797,000 bars, 43 MB of JSON, 323 MB resident and 125 s
#: of CPU on a laptop at load 40, whose CPU ran the same Black-Scholes loop 6-8x slower than the House box's.
#: G-LOOP (Sept 25, 2026, 19-21Z, the local copy again, one process at a time on an idle laptop; `measure_tape.py` in the
#: session's scratchpad): the same tape, May 21 - Sept 24 (2,262 steps), was 768,652 bars, 282 MB resident (367 bytes a
#: bar) and 4.8 s of CPU. With the reach (`_structure_reach`) and one object a number (`tape`), 565,906 bars: 95 MB live
#: (168 bytes a bar) and 170 MB resident (301 bytes a bar; 184 MB at the build's peak), 9.3 s of CPU. With every expiry of
#: SPY, QQQ and IWM ingested (`DAILY_EXPIRIES`) it will grow: the recorder's snapshots of Sept 25 show a weekday expiry
#: trading 0.36-1.16 times its Friday's (4.2 Fridays a week in all), and a reach shared by five expiries was measured as
#: one a fifth as wide on the weekly store (354,246 bars, 383 bytes a bar resident): an ESTIMATE of some 1.5 M bars for the
#: whole window. So 800,000 bars at most; over it the OLDEST steps go (`bounded`), which for a 0-7 day SPY/QQQ/IWM tape of
#: every expiry is estimated to keep the last two to three months of the House's four.
#: The cap is applied BEFORE any bar is read (the review of G-LOOP, Sept 25, 2026: applied after the build, a tape capped
#: at 150,000 bars still peaked at the uncapped 184 MB and kept 141 MB resident): `_structure_reach` counts what each step
#: would keep and `tape` reads bars only after the last step the cap drops. What a build then holds is the kept bars (168
#: bytes a bar live, 239-383 resident: some 135 MB live and 190-310 MB resident at the cap) plus the reach walk's own index
#: of the prints (4 bytes a print, a few hundred bytes a contract: 11 MB at its peak for the 768,652 prints above). Measured
#: after the fix on the same copy and window (`pin.py`, `measure_tape.py`): uncapped, 565,906 bars, peak RSS 151 MB (135 MB
#: resident, 8.3 s of CPU); capped at 150,000, 149,875 bars kept and a peak of 101 MB, where the review measured 184 MB for
#: both. The weekly store only: no copy holds every expiry yet, so that peak is to be measured on the box after the backfill.
STRUCTURE_TAPE_MAX_BARS = 800_000
#: A structure agent is shown the 80 contracts of an underlying nearest the money (`House._chain`, `options_replay`
#: STRUCTURE_CHAIN_PER_UNDERLYING), across every expiry it may trade. A structure tape keeps a contract's bars only if it
#: is ever among the `STRUCTURE_REACH` nearest (twice the 80: a leg a strategy names a few strikes past what it was shown
#: still has its market) of what the replay's chain could show at a step, from `STRUCTURE_LEAD_BARS` prints (the spread
#: estimate's `range_bars`) and the start of its New York day before it first is (`_structure_reach`, G-LOOP, Sept 25, 2026).
#: It is also a RULE, the same live and in replay (the review of G-LOOP, Sept 25, 2026): a structure is opened only when
#: every leg is among the `STRUCTURE_REACH` contracts of its underlying nearest the money that the chain could show at that
#: moment (`House._structure_reach_refusal`, `options_replay`). Without the rule, a leg past the reach was priced on a
#: reach-filtered tape only when the underlying LATER came near it (a look-ahead: the review's demonstration kept the
#: winning side of two far verticals and refused the losing one, in either direction); with it, which legs a structure
#: may name at a step depends only on the chain up to that step, and a tape keeps every bar such a leg could need.
STRUCTURE_REACH = 160
STRUCTURE_LEAD_BARS = 5
#: The replay's structure entry cut, New York minutes (`options_replay.STRUCTURE_ENTRY_CUT`, `House._structure_hours`).
STRUCTURE_ENTRY_CUT_MINUTES = 14 * 60 + 30
LIQUIDITY = {"min_volume": 5.0, "min_trades": 2, "max_participation": 0.10, "quote_age_seconds": 1500}
#: The underlyings whose EVERY expiry is ingested, not only the last of each week (G-LOOP, Sept 25, 2026): SPY, QQQ and IWM
#: list an expiry every weekday (95 in May 16 - Oct 2, 2026 each, on the local copy), and the store held their Fridays
#: alone, so a 0-2 day structure replay could trade only from Wednesday to Friday while the live chain shows a 0-DTE
#: expiry every day (the calibration study, row C of the options-desk run record).
DAILY_EXPIRIES = ("SPY", "QQQ", "IWM")
#: How many days before a weekday (non-weekly) expiry its bars are ingested: a structure replay reads a contract's bars
#: from `max_days_to_expiry + 4` days before its expiry, and the founders ask 10 at most; the weekly expiries keep the
#: store's `max_days` (45), as before. It holds the daily ingest to about a third of the 4.5 M bars (0.8-1 GB) the study
#: estimated for every expiry at 45 days.
DAILY_MAX_DAYS = 14
#: The most days to expiry a STRUCTURE program trading any of `DAILY_EXPIRIES` is shown (`structure_days`: the House's
#: chain, the tape and the replay alike): a weekday expiry's bars start `DAILY_MAX_DAYS` days before it, and a tape reads
#: a contract from four days before it may be shown (its spread estimate's history), so 10. Asking more, a program would
#: see Monday-Thursday expiries live from its `max_days_to_expiry` out and in replay only from 14 days out, without their
#: spread history (the review of G-LOOP, Sept 25, 2026). Every living structure agent that day asked 10 or fewer.
DAILY_SHOWN_DAYS = DAILY_MAX_DAYS - 4


def structure_days(asked: Any, symbols: Iterable[Any]) -> int:
    """How many days of expiries a STRUCTURE program with this `max_days_to_expiry` and these symbols is shown: its own
    answer (7 when unstated; 0 is a 0-DTE strategy's own answer, not "unsaid"), 45 at most, and `DAILY_SHOWN_DAYS` at
    most when any of its first eight symbols has every expiry ingested (`DAILY_EXPIRIES`). `House._structure_context`,
    `OptionsHistory.tape` and `options_replay` all read it, so the live chain and the replay's agree."""
    days = max(0, min(int(7 if asked is None else asked), 45))
    if any(str(s).upper() in DAILY_EXPIRIES for s in list(symbols or [])[:8]):
        days = min(days, DAILY_SHOWN_DAYS)
    return days
#: Alpaca charges no options commission (`league/fees.py`); the regulatory and clearing
#: pass-through (ORF, OCC, TAF) is not yet measured on this account. Assumed, per contract per fill.
FEE_PER_CONTRACT_USD = 0.05


class HistoryError(RuntimeError):
    """The venue refused or could not answer; the chunk stays unfinished."""


class StructureReach(NamedTuple):
    """What `OptionsHistory._structure_reach` found: occ -> the first bar kept; occ -> the step it was first among the
    reach; the last step the bar cap drops (None: none); the bars the tape would hold uncapped."""
    keep: dict[str, str]
    reached: dict[str, str]
    after: str | None
    total: int


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


def estimate_quote(bar: Mapping[str, Any], recent_ranges: Sequence[float], model: Mapping[str, Any] | None = None) -> tuple[float | None, float, float]:
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

    def covers(self, symbols: Iterable[str], timeframe: str, start: str, end: str, *, slack_days: int = 4,
               every_expiry: bool = False) -> list[str]:
        """The symbols whose recorded coverage of `timeframe` bars spans [start, end - slack]
        without a gap longer than `slack_days` (a weekend and a holiday). Start is clamped to
        the first day Alpaca holds any option history. `every_expiry`: only windows ingested with
        every expiry, not the last of each week alone (`ingest`'s `weekly_only` False for the symbol)."""
        want_start, want_end = _day(max(start[:10], HISTORY_STARTS)), _day(end[:10]) - timedelta(days=slack_days)
        held = []
        for symbol in symbols:
            spans = sorted((_day(r["start"]), _day(r["end"])) for r in self.coverage(symbol)
                           if r.get("timeframe") == timeframe and r.get("status") in ("complete", "current") and r.get("bars")
                           and not (every_expiry and r.get("weekly_only", True)))
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
               trades: bool = False, progress: Callable[[str], None] | None = None, all_expiries: Iterable[str] = (),
               daily_max_days: int | None = None) -> list[dict[str, Any]]:
        """Contracts, then bars (and optionally prints) of the near-the-money contracts of each
        underlying whose life overlaps [start, end]. Every chunk is journaled: an interrupted run
        resumes where it stopped, and a finished one costs nothing to run again.

        Selection: for each expiry E, the contracts whose strike is within `band` of the
        underlying's daily range over [E - max_days, E]. `weekly_only` keeps the last expiry of
        each week (SPY's daily expiries otherwise multiply the download five times); the replay
        chain then omits the others, which the live chain shows. `all_expiries` (G-LOOP, Sept 25,
        2026: `DAILY_EXPIRIES`) are the underlyings whose every expiry is kept whatever `weekly_only`
        says; an expiry that is not the last of its week is read from `daily_max_days` days before
        it (`DAILY_MAX_DAYS`) when given, else `max_days`. The weekly expiries' chunks are the same
        as a weekly ingest's, so what is stored is never fetched again."""
        say = progress or (lambda text: None)
        start = max(start[:10], HISTORY_STARTS)
        end = end[:10]
        today = ny_date(self.clock())
        every = {str(u).upper() for u in all_expiries}
        out = []
        for underlying in [u.upper() for u in underlyings]:
            weekly = weekly_only and underlying not in every
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
            last_of_week: dict[tuple[int, int], str] = {}
            for e in expiries:
                last_of_week[_day(e).isocalendar()[:2]] = e
            weeklies = set(last_of_week.values())
            if weekly:
                expiries = sorted(weeklies)
            for timeframe in timeframes:
                stats = {"contracts": 0, "with_bars": 0, "bars": 0, "failed_chunks": 0, "expiries": 0}
                asked: list[str] = []
                for expiry in expiries:
                    reach = max_days if expiry in weeklies or daily_max_days is None else min(max_days, int(daily_max_days))
                    win_start = max(_day(start), _day(expiry) - timedelta(days=reach))
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
                    "source": SOURCE_BARS, "listing": SOURCE_CONTRACTS, "band": band, "max_days": max_days, "weekly_only": weekly,
                    **({"daily_max_days": min(max_days, int(daily_max_days))} if not weekly and daily_max_days is not None else {}),
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
        than 5 prints that day are left out of the IV fields.

        SPY, QQQ and IWM (`DAILY_EXPIRIES`) are read on their WEEKLY expiries alone (the last listed of each week, as
        `ingest`'s `weekly_only`), whatever else the store holds: every stored row was made from the weekly store, and
        `compute_features` never remakes a day, so counting the weekday expiries once they are ingested would step
        `option_volume`, `contracts_printed` and `put_call_volume_ratio` up between old days and new (the adversarial
        review of Deploy G, Sept 25, 2026, on a synthetic every-expiry copy: SPY Sept 21 option_volume 702,366 ->
        2,461,369, contracts_printed 393 -> 1,024; QQQ Sept 18 put/call 1.84 -> 2.43), and replay (`feature_series`)
        and live (`features_at`) would read different series. `atm_iv` and `skew_25d` are unchanged by it."""
        symbol = symbol.upper()
        stamp = close_stamp(f"{day}T12:00:00Z", "1Day")  # available at the NY midnight after the session
        at_ts = datetime.combine(_day(day), datetime.min.time(), NY).replace(hour=16).timestamp()
        cur = self.db.execute("SELECT c.occ, c.expiry, c.strike, c.right, b.c, b.v, b.n FROM bars b JOIN contracts c ON c.occ = b.occ "
                              "WHERE c.underlying = ? AND b.timeframe = '1Day' AND b.t = ? AND c.expiry > ?", (symbol, stamp, day))
        rows = [dict(zip(("occ", "expiry", "strike", "right", "c", "v", "n"), r)) for r in cur]
        if symbol in DAILY_EXPIRIES and rows:
            listed = self.db.execute("SELECT DISTINCT expiry FROM contracts WHERE underlying = ? AND expiry > ?", (symbol, day))
            weekly = _weeklies(expiry for (expiry,) in listed)
            rows = [r for r in rows if r["expiry"] in weekly]
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
    def _every_expiry(self, symbol: str, execution: str, start: str, end: str) -> bool:
        """Whether a tape of `symbol` over [start, end] carries every expiry, not its weekly ones alone: always, unless the
        store's coverage of it is weekly -- recorded, yet not with every expiry across the window (`covers`; the G-LOOP
        review of Sept 25, 2026: while SPY, QQQ and IWM are backfilled with every expiry, a tape carries their Fridays
        alone, as it did before, rather than weekdays for part of its window). A store with no coverage row at all (a
        test's) is taken as it is."""
        if not self.coverage(symbol):
            return True
        return bool(self.covers([symbol], execution, start, end, every_expiry=True)) or not self.covers([symbol], execution, start, end)

    def _structure_reach(self, symbols: Sequence[str], listings: Mapping[str, Mapping[str, Mapping[str, Any]]],
                         closes: Mapping[str, Sequence[tuple[str, float]]], step_times: set[str], execution: str, start: str,
                         end: str, days: int, live: Mapping[str, Any], hours: Mapping[str, Sequence[int]], *,
                         model: Mapping[str, Any] | None = None, cap: int | None = None) -> StructureReach:
        """Which contracts a structure tape keeps, from when, and where its bar cap cuts it (G-LOOP, Sept 25, 2026).

        With every expiry of SPY, QQQ and IWM ingested (`DAILY_EXPIRIES`), a 0-7 day structure tape over the House's window
        was estimated at 4-5 times today's 768,652 bars (282 MB resident, measured on the local copy): some 1.4 GB, for a
        House killed for memory at 14:37Z that day. Yet a structure agent is shown only the 80 contracts of an underlying
        nearest the money, across all its expiries, and may open a structure only on legs among the `STRUCTURE_REACH`
        nearest at that moment (the rule, live and in replay). So this walks the steps as `options_replay` does -- the same
        bars (qualifying prints inside the tape's band and each contract's `days + 4`), a contract listed from its print
        within the quote age (or a recorded quote no older than its print), a bid shown (`display_quote` on the tape's own
        spread model), the expiry rules (none past, today's only before the entry cut, at most `days` out), the chain's 20%
        around the underlying's last close -- and ranks, at every step, the `STRUCTURE_REACH` nearest (ties as the replay
        breaks them). Returned:

        - `keep`: occ -> the first bar kept, for each contract that is ever among them: `STRUCTURE_LEAD_BARS` prints and the
          start of its New York day before its first such step, so its spread estimate, its day's volume and its quote are
          then what the whole tape would have given it. No other contract's bar is kept.
        - `reached`: occ -> that first step. The replay lists a contract, and lets a leg be opened, only from it (and only
          while it is among the nearest), so a bar kept for a later reach is never shown or traded before it: nothing a
          strategy sees or may open at a step depends on where the market went after it (the review of G-LOOP: without
          this, a far leg was priced only when the underlying later came near it).
        - `after`, `total`: with `cap`, the last step whose bars the cap drops (the OLDEST go: `bounded`), None when all fit,
          and how many bars the tape would hold uncapped. Counted here so `tape` never reads a dropped bar (the review:
          a cap applied after the build bounded neither the build's peak memory nor what the process kept)."""
        import heapq
        from array import array
        from collections import deque

        age = float(live["quote_age_seconds"])
        codes: list[str] = []
        info: list[tuple[str, float, str, date]] = []  # (underlying, strike, expiry, its date) by id
        ident: dict[str, int] = {}
        prints: dict[str, array] = {}  # step stamp -> ids that printed then (negative: its shown bid was None)
        times = set(step_times)
        for symbol in symbols:
            listed = listings.get(symbol) or {}
            stamps = [t for t, _ in closes.get(symbol, [])]
            prices = [c for _, c in closes.get(symbol, [])]
            names = list(listed)
            for i in range(0, len(names), 500):
                group = names[i:i + 500]
                marks = ",".join("?" * len(group))
                shown: dict[str, str] = {}
                for occ, t, c in self.db.execute(f"SELECT occ, t, c FROM bars WHERE timeframe = ? AND t >= ? AND t <= ? AND occ IN ({marks}) "
                                                 "AND v >= ? AND n >= ?", (execution, start, end, *group, float(live["min_volume"]), int(live["min_trades"]))):
                    row = listed[occ]
                    if occ not in shown:
                        shown[occ] = _shown_from(row["expiry"], days)
                    if t < shown[occ]:
                        continue
                    index = bisect.bisect_right(stamps, t) - 1
                    if index >= 0 and abs(float(row["strike"]) / prices[index] - 1.0) > STRUCTURE_BAND:
                        continue  # not on the tape (`tape`'s own band)
                    if t not in times:
                        if not _in_session(_ts(t)):
                            continue  # a bar with no step is not on the tape
                        times.add(t)
                    if occ not in ident:
                        ident[occ] = len(codes)
                        codes.append(occ)
                        info.append((symbol, float(row["strike"]), str(row["expiry"]), _day(row["expiry"])))
                    code = ident[occ] + 1
                    prints.setdefault(t, array("i")).append(-code if c is None or display_quote(float(c), model)[0] is None else code)
        ordered = sorted(times)
        quoted: dict[str, list[tuple[int, float]]] = {}  # step stamp -> (id, the quote's stamp): the last in (previous step, step]
        names = list(ident)
        for i in range(0, len(names), 500):
            group = names[i:i + 500]
            marks = ",".join("?" * len(group))
            last: dict[tuple[str, int], float] = {}
            for occ, t in self.db.execute(f"SELECT occ, t FROM quotes WHERE t >= ? AND t <= ? AND occ IN ({marks}) AND bid > 0 AND ask > bid "
                                          "ORDER BY occ, t", (start, end, *group)):
                index = bisect.bisect_left(ordered, t)
                if index < len(ordered):
                    last[(ordered[index], ident[occ])] = _ts(t)
            for (t, number), stamp in last.items():
                quoted.setdefault(t, []).append((number, stamp))
        spot_stamps = {s: [t for t, _ in closes.get(s, [])] for s in symbols}
        spot_prices = {s: [c for _, c in closes.get(s, [])] for s in symbols}
        seen: dict[int, tuple[float, bool]] = {}  # id -> (its last print's stamp, its shown bid was None)
        recorded: dict[int, float] = {}  # id -> its last recorded quote's stamp
        recent: deque[tuple[float, list[int]]] = deque()  # (stamp, ids printed or quoted then), within the quote age
        lead: dict[int, list[str]] = {}  # id -> the stamps of its last prints before it is first reached
        keep: dict[int, str] = {}  # id -> the first bar kept
        reached: dict[str, str] = {}
        for t in ordered:
            now = _ts(t)
            moment = datetime.fromtimestamp(now, NY)
            today, minute = moment.strftime("%Y-%m-%d"), moment.hour * 60 + moment.minute
            cut = int((hours.get(today) or (STRUCTURE_ENTRY_CUT_MINUTES,))[0])
            touched: list[int] = []
            for code in prints.get(t, ()):
                number = abs(code) - 1
                seen[number] = (now, code < 0)
                touched.append(number)
                if number not in keep:
                    stamps_before = lead.setdefault(number, [])
                    stamps_before.append(t)
                    if len(stamps_before) > STRUCTURE_LEAD_BARS:
                        del stamps_before[0]
            for number, stamp in quoted.get(t, ()):
                recorded[number] = stamp
                touched.append(number)
            recent.append((now, touched))
            while recent and now - recent[0][0] > age + 1e-9:
                recent.popleft()
            ranked: dict[str, list[tuple[float, str, str, int]]] = {}
            for number in {n for _, batch in recent for n in batch}:
                if number not in seen:
                    continue  # a recorded quote alone, with no print yet: not listed
                printed, dark = seen[number]
                real = recorded.get(number)
                if not ((real is not None and now - real <= age + 1e-9 and real >= printed) or (now - printed <= age + 1e-9 and not dark)):
                    continue
                symbol, strike, expiry, expires = info[number]
                if expiry < today or (expiry == today and minute >= cut) or (expires - moment.date()).days > days:
                    continue
                index = bisect.bisect_right(spot_stamps[symbol], t) - 1
                if index < 0:
                    continue  # no underlying price yet: no chain
                distance = abs(strike / spot_prices[symbol][index] - 1.0)
                if distance <= 0.20:  # the chain's moneyness line (`options_replay.chain`)
                    ranked.setdefault(symbol, []).append((distance, expiry, codes[number], number))
            for rows in ranked.values():
                for _, _, occ, number in heapq.nsmallest(STRUCTURE_REACH, rows):
                    if number not in keep:
                        day = iso(datetime.combine(moment.date(), datetime.min.time(), NY).timestamp())
                        keep[number] = min([day, *(lead.pop(number, None) or (t,))])
                        reached[occ] = t
        # What the tape would hold (a print kept from its contract's first kept bar on), and where the cap cuts it.
        counts: dict[str, int] = {}
        for t, batch in prints.items():
            n = sum(1 for code in batch if keep.get(abs(code) - 1, "~") <= t)
            if n:
                counts[t] = n
        total, after, held = sum(counts.values()), None, 0
        if cap is not None and total > cap:
            for t in sorted(counts, reverse=True):
                held += counts[t]
                if held > cap:
                    after = t  # this step's bars and every earlier one's are dropped
                    break
        return StructureReach({codes[number]: stamp for number, stamp in keep.items()}, reached, after, total)

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
        the local copy, Sept 25, 2026). Of those it keeps only the contracts its chain could ever reach, from a few prints
        before they first could, each carrying the step it first could (`reached`: the replay lists and trades it only from
        then; `_structure_reach`, G-LOOP, Sept 25, 2026). A structure tape is also held to `STRUCTURE_TAPE_MAX_BARS` option
        bars (`max_option_bars`): over it, the OLDEST steps are dropped (their signal bars joining the warmup), no bar of them
        is ever read, and the tape says so under `bounded`. A structure agent's days are `structure_days`'s.

        SPY, QQQ and IWM (`DAILY_EXPIRIES`) carry their weekly expiries alone until the store holds every expiry across the
        tape's window (`covers(every_expiry=True)`): while the backfill runs, part of a window would otherwise show a
        weekday expiry and the rest not (the review of G-LOOP, Sept 25, 2026). `every_expiry` says which each carries.
        NEEDS `structures` is read as the House reads it: `True` alone (1 or "true" is a single-contract program)."""
        symbols = [str(s).upper() for s in (needs.get("symbols") or [])][:8]
        structural = needs.get("structures") is True  # as `House.is_structure_agent` (the review of G-LOOP, Sept 25, 2026)
        asked = needs.get("max_days_to_expiry")
        # A structure agent's 0 is a 0-DTE strategy's own answer, not "unsaid" (`House._structure_context`).
        days = structure_days(asked, symbols) if structural else max(2, min(int(asked or 21), 45))
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
        # Every price and size a tape carries as one shared object (G-LOOP, Sept 25, 2026): sqlite hands each bar five new
        # floats (120 of the 288 bytes a bar held, measured on the local copy), and an option's prices repeat by the cent.
        # The same numbers, so the tape's JSON and every replay of it are what they were.
        numbers: dict[type, dict[Any, Any]] = {}

        def same(value: Any) -> Any:  # by type too: 1 == 1.0, and a trade count stays an int
            return numbers.setdefault(type(value), {}).setdefault(value, value)
        by_time: dict[str, dict[str, Any]] = {}
        for symbol, rows in execution_rows.items():
            for bar in rows:
                by_time.setdefault(bar["t"], {"execution_bars": {}, "options": {}})["execution_bars"][symbol] = {k: bar[k] for k in ("o", "h", "l", "c", "v")}
        first_day, last_day = ny_date(start_ts), (_day(ny_date(end_ts)) + timedelta(days=days)).isoformat()
        closes: dict[str, list[tuple[str, float]]] = {s: sorted((t, float(v["execution_bars"][s]["c"])) for t, v in by_time.items()
                                                              if s in v["execution_bars"]) for s in symbols}
        listings = {symbol: {r["occ"]: r for r in self.contracts(symbol, first_day, last_day)} for symbol in symbols}
        every_expiry = {symbol: self._every_expiry(symbol, execution, iso(start_ts), end) for symbol in symbols if symbol in DAILY_EXPIRIES}
        for symbol, every in every_expiry.items():
            if not every:
                weekly = _weeklies(r["expiry"] for r in self.contracts(symbol, first_day, (_day(last_day) + timedelta(days=6)).isoformat()))
                listings[symbol] = {occ: r for occ, r in listings[symbol].items() if r["expiry"] in weekly}
        spread_model = {**SPREAD_MODEL, **dict(spread or {})}
        cap = STRUCTURE_TAPE_MAX_BARS if max_option_bars is None else int(max_option_bars)
        # A structure tape keeps only the contracts its chain could ever reach (`_structure_reach`): occ -> the first
        # bar kept. Any other bar is dropped ("~" sorts after every stamp); so is every bar at or before `floor`, the
        # last step the cap drops (never read).
        reach = (self._structure_reach(symbols, listings, closes, set(by_time), execution, iso(start_ts), end, days, live,
                                       structure_hours(first_day, last_day), model=spread_model, cap=cap) if structural else None)
        floor = (reach.after or "") if reach is not None else ""
        for symbol in symbols:
            listed = listings[symbol]
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
                                      "AND v >= ? AND n >= ? AND t > ? ORDER BY occ, t", (*window, float(live["min_volume"]), int(live["min_trades"]), floor))
                current, kept = None, []

                def flush(occ: str | None, rows: list[tuple]) -> None:
                    # A superset of what any step could show: it printed, at some qualifying print
                    # its premium was within one order, and it was inside its last `days` (plus
                    # four for the spread estimate). A held contract was affordable when bought.
                    if occ is None or not rows or min(r[4] for r in rows) > afford:
                        return
                    row = listed[occ]
                    contracts[occ] = {"underlying": symbol, "expiry": row["expiry"], "strike": row["strike"], "right": row["right"],
                                      "first_print": first.get(occ) or rows[0][0],
                                      **({"reached": reach.reached[occ]} if reach is not None else {})}
                    for t, o, h, l, c, v, n in rows:
                        step = by_time.get(t)
                        if step is None and _in_session(_ts(t)):
                            step = by_time.setdefault(t, {"execution_bars": {}, "options": {}})
                        if step is not None:
                            # compact: o h l c v n, each number ONE object however many bars carry it (`same`)
                            step["options"][occ] = [same(o), same(h), same(l), same(c), same(v), same(n)]

                shown_from = ""
                for occ, t, o, h, l, c, v, n in cur:
                    if occ != current:
                        flush(current, kept)
                        current, kept = occ, []
                        shown_from = _shown_from(listed[occ]["expiry"], days)
                        if reach is not None:
                            shown_from = max(shown_from, reach.keep.get(occ, "~"))
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
            for occ, t, bid, ask in self.db.execute(f"SELECT occ, t, bid, ask FROM quotes WHERE t >= ? AND t <= ? AND occ IN ({marks}) AND t > ? "
                                                    "ORDER BY occ, t", (iso(start_ts), end, *group, floor)):
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
        kept = sum(len(entry["options"]) for entry in steps)
        total = reach.total if reach is not None and reach.after else kept
        if structural and total > cap:
            # The steps the cap drops (`floor`: their bars were never read), then -- only should the reach have counted fewer
            # bars than were read, which `test_structure_loop` pins never happens -- the oldest of the rest, as before.
            first = bisect.bisect_right([entry["t"] for entry in steps], floor) if floor else 0
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
        if reach is not None:
            reached = {"contracts": len(reach.keep), "listed": sum(len(v) for v in listings.values()), "reach": STRUCTURE_REACH,
                       "why": ("a structure tape keeps the contracts its chain could reach, from a few prints before they first could; "
                               "each is listed and traded only from the step it first could (`reached`)")}
        return {
            "venue": "alpaca", "asset_class": "option", "horizon": horizon, "timeframe": timeframe, "execution_timeframe": execution,
            "step_seconds": TIMEFRAMES[execution], "symbols": symbols, "warmup_bars": warmup_bars, "warmup_requested": warmup,
            "half_spread_bps": 1.0, "steps": steps, "contracts": contracts,
            "chain_rules": ({"max_days_to_expiry": days, "moneyness": 0.20, "per_underlying": 80, "afford_per_share": None, "structures": True,
                             "reach": STRUCTURE_REACH}
                            if structural else {"max_days_to_expiry": days, "moneyness": 0.20, "per_underlying": 40, "afford_per_share": afford}),
            "spread_model": spread_model, "liquidity": live,
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
            **({"reached": reached} if reach is not None else {}),
            **({"every_expiry": every_expiry} if every_expiry else {}),
            **({"structure_hours": structure_hours(first_day, last_day)} if structural else {}),
        }


def _weeklies(expiries: Iterable[str]) -> set[str]:
    """The last listed expiry of each ISO week (`ingest`'s `weekly_only`)."""
    last: dict[tuple[int, int], str] = {}
    for expiry in sorted(set(expiries)):
        last[_day(expiry).isocalendar()[:2]] = expiry
    return set(last.values())


def _shown_from(expiry: str, days: int) -> str:
    """The first stamp a tape keeps of a contract: New York midnight `days + 4` days before its expiry (a strategy may be
    shown it from `days` out; the four before feed its spread estimate)."""
    return iso(datetime.combine(_day(expiry) - timedelta(days=days + 4), datetime.min.time(), NY).timestamp())


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
            days: int = 10, timeframes: Sequence[str] = ("1Day",), band: float = 0.10, max_days: int = 45,
            all_expiries: Iterable[str] = (), daily_max_days: int | None = None) -> dict[str, Any]:
    """The House's daily job: the last `days` of bars for `symbols`, then their feature rows.
    The options desk's refresh must use the band of its backfill (0.2, the chain's own 20%),
    or the recent part of a tape would show fewer contracts than the older part. `all_expiries`
    and `daily_max_days`: `ingest`'s (every expiry of SPY, QQQ and IWM, since G-LOOP)."""
    end = ny_date(store.clock())
    start = (_day(end) - timedelta(days=days)).isoformat()
    coverage = store.ingest(symbols, start, end, underlier_bars=underlier_bars, timeframes=timeframes, band=band, max_days=max_days,
                            all_expiries=all_expiries, daily_max_days=daily_max_days)
    made = {}
    for symbol in symbols:
        daily = underlier_bars(symbol, "1Day", f"{start}T00:00:00Z", f"{end}T23:59:59Z")
        made[symbol] = store.compute_features(symbol, daily_closes(daily))
    return {"coverage": [{k: r.get(k) for k in ("underlying", "timeframe", "status", "bars")} for r in coverage], "features": made}


def main(argv: list[str] | None = None) -> int:
    """`python -m league.options_history ingest --symbols SPY,QQQ --start 2026-05-01 --end 2026-09-18`."""
    parser = argparse.ArgumentParser(description="Ingest listed-option history through the gateway (market-data GETs only).")
    parser.add_argument("command", choices=("ingest", "coverage", "features"))
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

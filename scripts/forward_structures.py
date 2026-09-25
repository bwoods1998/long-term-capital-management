#!/usr/bin/env python3
"""The structure founders' forward test on a session's RECORDED live OPRA snapshots, through the House's own code.

Sept 25, 2026 (the options-desk run's Wave 2, builder G-FORWARD). On Sept 25 a read-only recorder wrote one
snapshot a minute (15:10-20:01Z) of the live OPRA chain the House's gateway serves: SPY, QQQ and IWM expiries to
Oct 2 within 4% of spot, eleven stocks' Sept 25, Oct 2 and Oct 9 expiries within 12%, every contract's latest quote
WITH its size and time, its latest trade and minute bar, and each underlying's touch
(`~/Work/.options-history/live-2026-09-25.jsonl`, one JSON line a snapshot). The structure replay prices a leg
around its last 15-minute print; this is the other test: the twelve structure founders (`league/seeds/options_*.py`
but breakout and pullback, with their PARAMS) run on what the market really quoted, minute by minute.

**As the House runs them.** Each founder's `decide()` is called every `wake_minutes` on the context the House builds
for a structure agent, by the House's OWN methods borrowed onto a small stand-in (`HouseShim`): `House.snapshot`
(positions and open orders in held and natural prices, `recent_order_outcomes`, the rung-1 limits of $100 a position
and $75 an order), `_structure_context` (the chain through `_chain`/`_expiry_chain` with its two-minute cache, 0 to
`max_days_to_expiry` days, today's expiry until the 14:30 New York cut, 80 contracts an underlying nearest the money;
`ctx["structures"]` from `structures.candidates`; `ctx["structure_rules"]`), `_intents`/`_structure_intent`/
`_structure_refusal` (the House's refusals) and `_horizon_exits` (the entry cut and the 15:30 expiry-day close). The
orders go through the REAL `league.book.Book` (caps, the risk engine, marks every 300 s, one closed trade a
structure) into the REAL `league.options_shadow.OptionsShadowBroker`, whose fill rules are the live book's own: a fill
only on a quote of every leg strictly newer than the order's acceptance, opens at the structure's ask and closes at its
bid, 10% of each leg's shown size shared across orders, $0.05 a contract a leg, day orders, the session only. Its one
input is a leg-quote source serving each leg's quote AS OF the simulated minute (`LegSource`).

**No look-ahead.** A snapshot is available at the later of its start time and its newest quote's time (`Snapshot.t`):
no quote in it is later than that. The simulated clock moves from one snapshot's time to the next; a decision at time
t sees only snapshots available at or before t; the broker's quote source refuses to serve a snapshot from after the
clock (`LegSource`). Since an order is accepted at the clock of the snapshot its decision saw, and the broker fills
only on a leg quote newer than that, every fill is on a strictly newer snapshot. The output's `checks` count both, and
re-derive every fill from the raw snapshot it was made on, apart from the broker's code (`audit_fill`: the touch, legs
quoted after the acceptance, sizes); `league/tests/test_forward_structures.py` pins them.

**What is not the House's** (said in the output): the chain rows carry Black-Scholes IV and delta from each contract's
mid (r 4%, `options_history.implied_vol`), where the live chain carries Alpaca's greeks (the recorder did not keep
them; measured against the House's recorded chains on contracts of 1 day or more, within 0.003 of delta at the median,
0.01 at p90), and none on a contract expiring today, as live; the recorded bands (4% of spot on the ETFs, 12% on the
stocks) are narrower than the chain's 20%; the underlying bars are the House's own recordings of the day
(`recordings.sqlite`, read-only, `--house-bars`), completed from the local history (`underlier_bars`) and, failing
both, from the snapshots' mids; the tick is one a snapshot (60 s; the live House's ticks ran 60-200 s).

**When a floor starts** (reviewed Sept 25): on the first snapshot with leg sizes AND a spot for every symbol its
founders trade (`RunConfig.require_spots`). On Sept 25 the recorder's first line has no sizes and its second only the
ETFs (no stock row or spot until 15:12:02Z), so a floor started there showed the stock founders a price of 0 and
orb one symbol of five. The recording itself begins at 15:10Z: the session's first 1 h 40 min (the opening range, 70
minutes of condor-vrp's entry window) is not in it, and the output says "the recorded session", never the whole one.

**One figure is one path** (reviewed Sept 25). The House's structure chains are cached two minutes and shared by
every structure agent reading the same underlying, so what a founder sees depends on which founders share its
House and on the minute it wakes. `run_many` drives many independent floors (each its own House caches, book, broker
and ledger) over ONE pass of the file; `paths` runs every founder alone and all together from several start
snapshots and gives each figure as a range.

The comparison with the live House: the live structure founders' own rows (`live_query`), a second run from each
live founder's first wake (`--from-birth`), the thoughts of both digested by wake (`thought_agreement`), and the
chains the House recorded against the forward chain (`chains_query`, `compare_chains`). The House changed in the
session: from 18:33:52Z (Deploy V4, PR #339) it re-prices a structure limit further through its touch than the book's
10% band to the band's edge (`House._fit_structure_limit`); `HouseShim.reprice_from` runs the House of either
release, or the switch as the floor made it. A labelled what-if (`--what-if-0dte-greeks`, never the House) gives
today's expiries Black-Scholes greeks, which nothing has validated on a same-day contract (Alpaca gives none to
compare with); `zero_dte_exposure` says which founders it bears on. Each fill's bid-ask paid against the structure's
mid is measured on the snapshot it was made on (`spread_of_fill`: scoreboard metric 4). `calibrate` refits
s3/calibration's fill half-spread table with the day's recorded quotes.

**Inputs** (`--day`): the snapshots `~/Work/.options-history/live-<day>.jsonl` and, beside them, the three read-only
query outputs `house-bars-<day>.json`, `house-live-<day>.json`, `house-chains-<day>.json` (the queries' text is
printed for the day by `query-bars|query-live|query-chains`); the output records each file's sha256.

Usage (ONE process at a time on the shared machine; it streams the file once, about 20 s, plus the floors' work):
    python3 scripts/forward_structures.py --day 2026-09-25 query-bars|query-live|query-chains   # the read-only queries (rx.py)
    python3 scripts/forward_structures.py --day 2026-09-25 --from-birth --before-v4 --what-if-0dte-greeks --paths 5 \
        --until 2026-09-25T20:00:00Z --out forward.json
    python3 scripts/forward_structures.py --day 2026-09-25 calibrate --fit-from s3_options_history.py --out calibration.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sqlite3
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from league import niches as niches_module  # noqa: E402
from league import structure_core as core  # noqa: E402
from league import structures  # noqa: E402
from league.book import Book, Limits  # noqa: E402
from league.fees import Fees  # noqa: E402
from league.house import House  # noqa: E402
from league.ledger import Ledger  # noqa: E402
from league.options_history import implied_vol, bs_delta, years_to  # noqa: E402
from league.options_shadow import NEW_YORK, OptionsShadowBroker, stamp  # noqa: E402
from league.venues import market_hours  # noqa: E402

#: The twelve structure founders on main (Sept 25, 2026): every `league/seeds/options_*.py` but the two single-leg
#: founders (breakout, pullback).
FOUNDERS = ("options_butterfly_pin", "options_calendar_term", "options_condor_vrp", "options_diagonal", "options_gap_drift",
            "options_ironfly_quiet", "options_orb", "options_putspread_dip", "options_reversal", "options_skew",
            "options_strangle_cheap", "options_trend_vertical")
BOOK = "options-shadow"
#: The rung-1 seat on the practice book (`constitution.json` rungs.1): the stake and the caps an agent is shown.
STAKE = Decimal(200)
LIMITS = (Decimal(100), Decimal(75))
MARK_EVERY = 300.0  # `config.json` mark_every_seconds


def parse_ts(text: Any) -> float | None:
    """An ISO stamp (nanoseconds allowed) as epoch seconds; None when it is not one."""
    if not isinstance(text, str) or not text.strip():
        return None
    value = stamp(text)
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class SimClock:
    """The simulated clock every component reads (`Book`, the broker, the ledger, the House's methods)."""

    def __init__(self, now: float = 0.0):
        self.now = float(now)

    def __call__(self) -> float:
        return self.now


# ------------------------------------------------------------------------------------------ the snapshots
@dataclass
class Snapshot:
    """One recorded snapshot: `t` is when it was available (its start or its newest quote, the later), `index` its
    line, `spot` each underlying's (bid, ask), `rows` each contract's recorded row by OCC code."""

    index: int
    t: float
    at: float
    version: int
    spot: dict[str, tuple[float, float]]
    rows: dict[str, dict[str, Any]]


KEEP = ("underlying", "expiry", "strike", "right", "bid", "ask", "bid_size", "ask_size", "as_of", "volume", "last", "last_t", "mbar")


def read_snapshots(path: str | Path, *, until: float | None = None) -> Iterator[Snapshot]:
    """Stream the recorder's file one line at a time (it is about a megabyte a line). A line that is not whole JSON
    (the recorder is writing it) ends the stream; `until` stops before a snapshot available after it."""
    with open(path, encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except ValueError:
                return
            at = parse_ts(raw.get("at"))
            if at is None:
                continue
            rows: dict[str, dict[str, Any]] = {}
            newest = at
            for row in raw.get("rows") or ():
                occ = str(row.get("symbol") or "").upper()
                if not occ:
                    continue
                kept = {k: row.get(k) for k in KEEP}
                kept["as_of"] = stamp(row.get("as_of")) if row.get("as_of") else None
                moment = parse_ts(kept["as_of"]) if kept["as_of"] else None
                if moment is not None:
                    newest = max(newest, moment)
                rows[occ] = kept
            spot = {}
            for symbol, touch in (raw.get("spot") or {}).items():
                try:
                    bid, ask = float(touch.get("bid")), float(touch.get("ask"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if 0 < bid <= ask:
                    spot[str(symbol).upper()] = (bid, ask)
            snap = Snapshot(index, newest, at, int(raw.get("v") or 1), spot, rows)
            if until is not None and snap.t > until:
                return
            yield snap


class LegSource:
    """The broker's leg-quote reader (`OptionsShadowBroker.leg_quotes`): the current snapshot's rows in the
    production reader's shape (`alpaca_leg_quotes`: Decimals, sizes, the quote time to the microsecond). It never
    serves a snapshot available after the clock: that would be a fill on a quote nobody had yet."""

    def __init__(self, clock: SimClock):
        self.clock = clock
        self.current: Snapshot | None = None
        self.served: list[tuple[float, int]] = []  # (clock, snapshot index) of each read, for the checks

    def __call__(self, occs: Sequence[str]) -> dict[str, dict[str, Any]]:
        snap = self.current
        if snap is None:
            return {}
        if snap.t > self.clock() + 1e-9:
            raise AssertionError(f"look-ahead: snapshot {snap.index} is available at {iso(snap.t)}, the clock is {iso(self.clock())}")
        self.served.append((self.clock(), snap.index))
        out = {}
        for occ in occs:
            row = snap.rows.get(str(occ).upper())
            if row is None:
                continue
            out[str(occ).upper()] = {"bid": _dec(row.get("bid")), "ask": _dec(row.get("ask")), "bid_size": _dec(row.get("bid_size")),
                                     "ask_size": _dec(row.get("ask_size")), "as_of": row.get("as_of")}
        return out


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
    except ArithmeticError:
        return None
    return out if out.is_finite() else None


class ChainBroker:
    """What `House._chain` reads a chain from (`broker.option_chain`), over the current snapshot, in the adapter's
    shape (`ltcm/adapters/alpaca.py` `option_chain`): two-sided rows only (0 < bid < ask), nearest expiry and lowest
    strike first. `iv` and `delta` are Black-Scholes from the mid against the underlying's mid (r 4%), the recorder
    having kept no greeks, and None on a contract expiring today, as Alpaca's feed gives them (`compare_chains`
    measures both against the chains the House recorded)."""

    option_feed = "opra"

    def __init__(self, source: LegSource, *, zero_dte_greeks: bool = False):
        self.source = source
        self.zero_dte_greeks = zero_dte_greeks  # a WHAT-IF: greeks on today's expiries too (the live feed has none)
        self._greeks: dict[tuple[int, str], tuple[float | None, float | None]] = {}  # the current snapshot's, shared by every floor

    def option_chain(self, underlying: str, *, expiry_from: str, expiry_to: str, limit: int = 1000) -> list[dict[str, Any]]:
        snap = self.source.current
        if snap is None:
            return []
        clock = self.source.clock()
        if snap.t > clock + 1e-9:
            raise AssertionError("look-ahead in the chain")
        if self._greeks and next(iter(self._greeks))[0] != snap.index:
            self._greeks.clear()
        under = underlying.upper()
        today = datetime.fromtimestamp(clock, NEW_YORK).strftime("%Y-%m-%d")
        spot = snap.spot.get(under)
        mid_spot = (spot[0] + spot[1]) / 2 if spot else None
        out = []
        for occ, row in snap.rows.items():
            if row.get("underlying") != under or not (expiry_from <= str(row.get("expiry")) <= expiry_to):
                continue
            bid, ask = row.get("bid"), row.get("ask")
            if bid is None or ask is None or not (0 < float(bid) < float(ask)):
                continue
            key = (snap.index, occ)
            if key not in self._greeks:
                # As the live feed: Alpaca's snapshot carries no greeks on a contract expiring today (the House's recorded
                # chains of Sept 25: none on 12,882 of 12,882 0-DTE index rows and 7,986 of 7,986 0-DTE stock rows).
                self._greeks[key] = (None, None) if str(row.get("expiry")) <= today and not self.zero_dte_greeks else greeks(row, mid_spot, snap.t)
            iv, delta = self._greeks[key]
            out.append({"symbol": occ, "underlying": under, "expiry": str(row["expiry"]), "strike": float(row["strike"]),
                        "right": str(row["right"]), "bid": float(bid), "ask": float(ask), "as_of": row.get("as_of"),
                        "iv": iv, "delta": delta, "volume": None if row.get("volume") is None else float(row["volume"])})
        out.sort(key=lambda r: (r["expiry"], r["strike"], r["right"]))
        return out[:limit]


def greeks(row: Mapping[str, Any], spot: float | None, at: float) -> tuple[float | None, float | None]:
    """(iv, delta) by Black-Scholes from the row's mid, or (None, None) where no volatility prices it."""
    try:
        mid = (float(row["bid"]) + float(row["ask"])) / 2
        years = years_to(str(row["expiry"]), at)
        if not spot or years <= 0:
            return None, None
        vol = implied_vol(mid, spot, float(row["strike"]), years, str(row["right"]))
        if vol is None:
            return None, None
        return round(vol, 6), round(bs_delta(spot, float(row["strike"]), years, vol, str(row["right"])), 6)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None


# ------------------------------------------------------------------------------------------ the underlying's bars
class Bars:
    """The underlying bars a strategy is shown (`AlpacaData.bars`: close-stamped, closed bars only, the last `limit`)
    and the touch (`AlpacaData.quotes`), as of the simulated clock. Bars come from, in order of trust: the House's own
    recordings of the day (`--house-bars`: the payloads `House._cached` recorded for these very keys), the local
    history's `underlier_bars`, and the snapshots' mids (only for what neither holds)."""

    TIMEFRAMES = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86400}

    def __init__(self, clock: SimClock, source: LegSource):
        self.clock = clock
        self.source = source
        self.series: dict[tuple[str, str], dict[float, dict[str, Any]]] = {}
        self.origin: dict[tuple[str, str], dict[float, str]] = {}
        self.minutes: dict[str, list[tuple[float, float]]] = {}  # symbol -> [(snapshot time, mid)]
        self._sorted: dict[tuple[str, str], list[tuple[float, dict[str, Any]]]] = {}
        self.from_mids: dict[str, int] = {}  # "SYMBOL:timeframe" -> how many times a wake was shown a bar built from mids

    def add(self, symbol: str, timeframe: str, bars: Sequence[Mapping[str, Any]], origin: str, *, replace: bool) -> None:
        key = (symbol.upper(), timeframe)
        series = self.series.setdefault(key, {})
        where = self.origin.setdefault(key, {})
        for bar in bars:
            t = parse_ts(bar.get("t"))
            if t is None or (not replace and t in series):
                continue
            series[t] = {k: bar[k] for k in ("t", "o", "h", "l", "c", "v") if k in bar}
            where[t] = origin
        self._sorted.pop(key, None)

    def sources(self) -> dict[str, dict[str, int]]:
        """How many bars of each series came from each source (the House's recordings, the local history)."""
        out = {}
        for (symbol, timeframe), where in sorted(self.origin.items()):
            counts: dict[str, int] = {}
            for origin in where.values():
                counts[origin] = counts.get(origin, 0) + 1
            if counts:
                out[f"{symbol}:{timeframe}"] = counts
        return out

    def load_house(self, payload: Mapping[str, Any]) -> None:
        """BARS_QUERY's output (`bars_query`): every recorded key's earliest and latest payload."""
        for key, recs in (payload.get("bars") or {}).items():
            timeframe = key.split(":")[2]
            for label in ("earliest", "latest"):  # the latest recording's bars replace the earliest's
                value = ((recs or {}).get(label) or {}).get("value") or {}
                for symbol, rows in value.items():
                    self.add(symbol, timeframe, rows, "house", replace=True)

    def load_local(self, store: str | Path, symbols: Sequence[str], timeframes: Sequence[str], before: float) -> None:
        db = sqlite3.connect(f"file:{Path(store).expanduser()}?mode=ro", uri=True)
        try:
            for symbol in symbols:
                for timeframe in timeframes:
                    rows = db.execute("SELECT payload FROM underlier_bars WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                                      (symbol, timeframe, before - 86400 * 120, before)).fetchall()
                    self.add(symbol, timeframe, [json.loads(r[0]) for r in rows], "local", replace=False)
        finally:
            db.close()

    def observe(self, snap: Snapshot) -> None:
        for symbol, (bid, ask) in snap.spot.items():
            self.minutes.setdefault(symbol, []).append((snap.t, (bid + ask) / 2))

    def _closed(self, symbol: str, timeframe: str) -> list[tuple[float, dict[str, Any]]]:
        key = (symbol, timeframe)
        if key not in self._sorted:
            self._sorted[key] = sorted(self.series.get(key, {}).items())
        return self._sorted[key]

    def _from_mids(self, symbol: str, timeframe: str, have_until: float, now: float) -> list[dict[str, Any]]:
        """Bars closed after `have_until` and by `now` built from the snapshots' mids (volume 0), for a key whose
        recorded bars stop before the clock. Only a bar whose whole span the snapshots saw."""
        seconds = self.TIMEFRAMES.get(timeframe)
        if not seconds or timeframe == "1Day":
            return []
        points = [(t, p) for t, p in self.minutes.get(symbol, []) if have_until < t <= now]
        out: dict[float, list[float]] = {}
        for t, price in points:
            close = math.ceil(t / seconds) * seconds
            out.setdefault(close, []).append(price)
        first_seen = self.minutes.get(symbol, [(now, 0)])[0][0]
        bars = []
        for close, prices in sorted(out.items()):
            if close > now or close - seconds < first_seen or close <= have_until:
                continue
            bars.append({"t": iso(close).replace(".000000Z", "Z"), "o": prices[0], "h": max(prices), "l": min(prices), "c": prices[-1], "v": 0.0,
                         "_from": "snapshot mids"})
        return bars

    def bars(self, symbols: Sequence[str], timeframe: str, *, limit: int = 120, start: Any = None, end: Any = None) -> dict[str, list[dict[str, Any]]]:
        now = self.clock()
        out = {}
        for symbol in symbols:
            symbol = str(symbol).upper()
            rows = [bar for t, bar in self._closed(symbol, timeframe) if t <= now]
            have_until = parse_ts(rows[-1]["t"]) if rows else 0.0
            built = self._from_mids(symbol, timeframe, have_until or 0.0, now)
            if built:
                self.from_mids[f"{symbol}:{timeframe}"] = self.from_mids.get(f"{symbol}:{timeframe}", 0) + 1
            rows = rows + built
            out[symbol] = [dict(bar) for bar in rows[-int(limit):]]
        return out

    def quotes(self, symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
        snap = self.source.current
        if snap is None:
            return {}
        out = {}
        for symbol in symbols:
            touch = snap.spot.get(str(symbol).upper())
            if touch:
                out[str(symbol).upper()] = {"bid": touch[0], "ask": touch[1], "t": iso(snap.at)}
        return out


class Features:
    """`options_features` for a strategy that asks for them (`House.snapshot`: `options_history.features_at`): the
    latest `bs-close-v2` row available by the clock, from the House's own rows of the day when given (BARS_QUERY's
    `features`: the box's store, read-only) and the local copy of the store (through Sept 24), whichever is later.
    Nothing is ever written to either; `served` counts where each answer came from."""

    VERSION = "bs-close-v2"

    def __init__(self, store: str | Path | None, rows: Sequence[Mapping[str, Any]] = ()):
        self.path = None if store is None else Path(store).expanduser()
        self.house: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        for row in rows or ():
            at = parse_ts(row.get("available_at"))
            if at is not None and row.get("version") == self.VERSION and isinstance(row.get("payload"), dict):
                self.house.setdefault(str(row.get("symbol") or "").upper(), []).append((at, row["payload"]))
        for found in self.house.values():
            found.sort(key=lambda pair: pair[0])
        self.served = {"house": 0, "local": 0}

    def features_at(self, symbols: Sequence[str], now_ts: float) -> dict[str, Any]:
        out: dict[str, tuple[float, dict[str, Any], str]] = {}
        for symbol in symbols:
            ready = [pair for pair in self.house.get(str(symbol).upper(), []) if pair[0] <= now_ts]
            if ready:
                out[str(symbol).upper()] = (ready[-1][0], ready[-1][1], "house")
        if self.path is not None and self.path.exists():
            db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            try:
                for symbol in symbols:
                    row = db.execute("SELECT available_at, payload FROM features WHERE symbol = ? AND version = ? AND available_at <= ? "
                                     "ORDER BY available_at DESC LIMIT 1", (str(symbol).upper(), self.VERSION, iso(now_ts))).fetchone()
                    at = parse_ts(row[0]) if row else None
                    if at is not None and at <= now_ts and at > out.get(str(symbol).upper(), (-1.0,))[0]:
                        out[str(symbol).upper()] = (at, json.loads(row[1]), "local")
            finally:
                db.close()
        for _, _, where in out.values():
            self.served[where] += 1
        return {symbol: payload for symbol, (_, payload, _) in out.items()}


# ------------------------------------------------------------------------------------------ the House, borrowed
class _Registry:
    def entries_paused(self, agent_id: str) -> None:
        return None


class _Evaluator:
    def rung(self, agent_id: str) -> int:
        return 1


class _Recorder:
    def record(self, key: str, value: Any, *, started: float) -> None:
        return None


BORROWED = ("snapshot", "_stamped", "_structure_context", "_structure_hours", "_structure_book_name", "_chain", "_expiry_chain",
            "_trading_days", "_read_expiry", "_cached", "_opened_since", "_session_open", "_structure_row", "_real_limits",
            "is_structure_agent", "niche_of", "_feeds_wanted", "_intents", "_structure_intent", "_structure_refusal",
            "_refuse_intent", "_horizon_exits", "_cancel_structure_opens_at_cut", "_structure_expiry_close", "_structure_bid",
            "_structure_resting", "_structure_sale")


class HouseShim:
    """The House's own structure methods (`BORROWED`, taken from `league.house.House` as they are) over the
    simulated books, clock and market data: no House is built, nothing else of it runs."""

    structure_book_name = BOOK

    def __init__(self, clock: SimClock, ledger: Ledger, books: dict[str, Any], data: Bars, features: Features):
        self.clock = clock
        self.ledger = ledger
        self.books = books
        self.alpaca_data = data
        self.options_history = features
        self.feeds = None
        self.registry = _Registry()
        self.evaluator = _Evaluator()
        self.recorder = _Recorder()
        self.niches = niches_module.load()
        self._data_cache: dict[str, Any] = {}
        self._opens: dict[str, Any] = {}
        self._state: dict[str, Any] = {"memory": {}}
        self.alerts: list[tuple[str, str, str]] = []
        self.repriced: dict[str, int] = {}  # agent -> structure limits the House re-priced to the book's band

    def alert(self, level: str, text: str) -> None:
        self.alerts.append((iso(self.clock()), level, text[:400]))

    def _keep_option_quotes(self, broker: Any, chain: Any, spot: Any) -> None:
        return None  # the live House keeps them in its options history; the forward test writes nothing

    #: From when the House re-prices a structure order further through its touch than the book's 10% band to the
    #: band's edge (`House._fit_structure_limit`, PR #339, on the floor from 18:33:52Z Sept 25 with release
    #: 20260925T183013Z-19fb86ee4720): None always (the House on main now), `float("inf")` never (the House of
    #: 16:36-18:33Z, release 20260925T163626Z-46eda79f4052), or the epoch it began (the day as the floor ran it).
    reprice_from: float | None = None

    def _fit_structure_limit(self, book: Any, intent: Any, *, nonce: str) -> Any:
        if self.reprice_from is not None and self.clock() < self.reprice_from:
            return intent
        fitted = vars(House)["_fit_structure_limit"](self, book, intent, nonce=nonce)
        if fitted is not intent:
            self.repriced[intent.agent] = self.repriced.get(intent.agent, 0) + 1
        return fitted


for _name in BORROWED:
    setattr(HouseShim, _name, vars(House)[_name])


class _ChainBook:
    """What `House._chain` looks for among the books: an Alpaca book whose broker lists a chain."""

    def __init__(self, broker: ChainBroker):
        self.broker = broker


# ------------------------------------------------------------------------------------------ the founders
def load_founder(name: str) -> SimpleNamespace:
    path = REPO / "league" / "seeds" / f"{name}.py"
    source = path.read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"forward_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    needs = dict(module.NEEDS)
    family = str(needs.get("style") or name.replace("_", "-"))
    return SimpleNamespace(id=f"fwd-{family}", family=family, founder=family, seed=name, needs=needs, params=dict(module.PARAMS),
                           venue="alpaca", horizon=str(needs.get("horizon") or "day"), wake_minutes=float(needs.get("wake_minutes") or 10),
                           specialty="alpaca-options", code=source, decide=module.decide, alive=True)


_NUMBER = re.compile(r"(?:(?<![\w.])[-+])?\$?\d[\d,]*(?:\.\d+)?(?:%|x\b)?")  # a sign only where it starts the number


def digest(thought: str) -> str:
    """A thought with its numbers taken out (prices, times, ratios, strikes all read '#'): what a founder SAID at a
    wake, so the forward twin and the live agent can be compared although their quotes are a minute apart."""
    return re.sub(r"\s+", " ", _NUMBER.sub("#", str(thought or ""))).strip()[:240]


def runs_of(rows: Sequence[tuple[str, str]]) -> list[list[Any]]:
    """[(at, digest)] as runs of one digest: [first at, last at, wakes, digest]."""
    out: list[list[Any]] = []
    for at, text in rows:
        if out and out[-1][3] == text:
            out[-1][1] = at
            out[-1][2] += 1
        else:
            out.append([at, at, 1, text])
    return out


@dataclass
class Tally:
    wakes: int = 0
    errors: int = 0
    last_error: str = ""
    intents: int = 0
    dropped: list[str] = field(default_factory=list)
    thoughts: list[tuple[str, str]] = field(default_factory=list)
    digests: list[tuple[str, str]] = field(default_factory=list)  # every wake's (at, digest(thought))
    decisions: list[dict[str, Any]] = field(default_factory=list)


# ------------------------------------------------------------------------------------------ the run
def founder_symbols(agents: Sequence[Any]) -> list[str]:
    return sorted({str(s).upper() for a in agents for s in a.needs.get("symbols") or ()})


@dataclass
class RunConfig:
    """One simulated floor. Its `founders` share one House: the House's two-minute structure-chain caches are
    shared by every structure agent reading the same underlying, so who runs together changes what each one sees.
    Its book starts on the first snapshot at or after `start` with leg sizes and a spot of every symbol in
    `require_spots` (its founders' symbols when None), after skipping `start_after` such snapshots (the tick phase);
    `starts` holds a founder back until its own first wake (the live birth, for the comparison); `reprice_from` says
    from when the House re-prices a structure limit beyond the book's band (`HouseShim.reprice_from`);
    `zero_dte_greeks` is a WHAT-IF, not the House: Black-Scholes greeks on today's expiries, which the live feed does
    not carry; `decide_override` replaces a founder's decide (the tests)."""

    label: str = "forward"
    founders: Sequence[str] = FOUNDERS
    start: float | None = None
    start_after: int = 0
    starts: Mapping[str, float] | None = None
    reprice_from: float | None = None
    zero_dte_greeks: bool = False
    decide_override: Mapping[str, Callable[[dict], dict]] | None = None
    keep_thoughts: int = 6
    mark_every: float = MARK_EVERY
    require_spots: Sequence[str] | None = None


class Market:
    """What every floor of one pass shares: the clock, the current snapshot, the underlying's bars and features,
    and the chain readers (without and with the what-if's greeks on today's expiries), whose Black-Scholes is
    computed once a snapshot. None of it is a House's state: each floor keeps its own House caches, book, broker,
    ledger and clock-driven marks."""

    def __init__(self, clock: SimClock, *, house_bars: str | Path | None, local_store: str | Path | None,
                 symbols: Sequence[str], timeframes: Sequence[str]):
        self.clock = clock
        self.source = LegSource(clock)
        self.bars = Bars(clock, self.source)
        rows: Sequence[Mapping[str, Any]] = ()
        if house_bars:
            payload = json.loads(Path(house_bars).read_text(encoding="utf-8"))
            self.bars.load_house(payload)
            rows = payload.get("features") or ()
        self.features = Features(local_store, rows)
        self.chains = {flag: ChainBroker(self.source, zero_dte_greeks=flag) for flag in (False, True)}
        self.local_store = local_store
        self.symbols, self.timeframes = list(symbols), list(timeframes)
        self.local_loaded_before: float | None = None

    def observe(self, snap: Snapshot) -> None:
        self.clock.now = snap.t
        self.source.current = snap
        self.bars.observe(snap)

    def load_local(self, before: float) -> None:
        """The local history's underlier bars, once, when the first floor starts (they end the day before)."""
        if self.local_store and self.local_loaded_before is None:
            self.bars.load_local(self.local_store, self.symbols, self.timeframes, before)
            self.local_loaded_before = before


class Floor:
    """One simulated floor over the market's snapshots: its founders, the House's methods over its own caches
    (`HouseShim`), the real `Book` and `OptionsShadowBroker` on its own ledger. `step` is the House's tick."""

    def __init__(self, market: Market, config: RunConfig, root: Path):
        self.market, self.config, self.clock = market, config, market.clock
        clock = market.clock
        self.source = LegSource(clock)  # the broker's own reader, so its reads count for this floor alone
        self.agents = [load_founder(name) for name in config.founders]
        for agent in self.agents:
            if config.decide_override and agent.seed in config.decide_override:
                agent.decide = config.decide_override[agent.seed]
        wanted = config.require_spots if config.require_spots is not None else founder_symbols(self.agents)
        self.require = {str(s).upper() for s in wanted}
        root.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(root / "ledger.sqlite", clock=clock)
        self.broker = OptionsShadowBroker(root / "options-shadow.json", self.source, underlying_close=None, starting_cash="100000", clock=clock)
        self.book = Book(BOOK, self.broker, self.ledger, fees=Fees("alpaca", option_clearing=True), real_money=False, clock=clock,
                         market_open=market_hours)
        books = {"alpaca-paper": _ChainBook(market.chains[bool(config.zero_dte_greeks)]), BOOK: self.book}
        self.shim = HouseShim(clock, self.ledger, books, market.bars, market.features)
        self.shim.reprice_from = config.reprice_from
        self.tallies = {a.id: Tally() for a in self.agents}
        self.next_wake: dict[str, float] = {}
        self.last_mark = -1e18
        self.checks: dict[str, Any] = {
            "decisions": 0, "decision_snapshot_after_clock": 0, "fills": 0, "fills_not_on_newer_snapshot": 0, "fills_failing_audit": 0,
            "snapshots": 0, "first_snapshot": None, "last_snapshot": None, "sized_from": None, "started_from": None,
            "start_rule": f"the first snapshot with leg sizes and a spot of {','.join(sorted(self.require))}, after {config.start_after} such"}
        self.decided_on: dict[str, list[tuple[float, int]]] = {}  # agent -> [(decision clock, snapshot index)]
        self.fill_snapshot: dict[str, int] = {}
        self.submitted_at: dict[str, float] = {}
        self.fill_log: list[dict[str, Any]] = []
        self.spread: dict[int, dict[str, Any]] = {}  # ledger seq of a fill -> `spread_of_fill`
        self.fill_seq = 0
        self.skipped = 0
        self.started = False
        self.last: Snapshot | None = None

    def step(self, snap: Snapshot) -> None:
        config, clock, book, checks = self.config, self.clock, self.book, self.checks
        if config.start is not None and snap.t < config.start:
            return
        self.source.current = snap
        self.last = snap
        checks["snapshots"] += 1
        checks["first_snapshot"] = checks["first_snapshot"] or iso(snap.t)
        checks["last_snapshot"] = iso(snap.t)
        if not any(r.get("bid_size") is not None for r in snap.rows.values()):
            return  # no leg sizes (the recorder's first line): the broker could fill nothing on it; nothing starts on it
        checks["sized_from"] = checks["sized_from"] or iso(snap.t)
        if not self.started:
            if not self.require <= set(snap.spot):
                return  # a symbol has no touch yet (Sept 25's second line: the ETFs only): its founder would see a price of 0
            if self.skipped < config.start_after:
                self.skipped += 1
                return
            self.started = True
            checks["started_from"] = iso(snap.t)
            self.market.load_local(snap.t)
            for agent in self.agents:
                book.stake(agent.id, STAKE, note="rung 1 stake")
                book.limits[agent.id] = Limits(LIMITS[0], LIMITS[1], asset_classes=("option",))
                self.next_wake[agent.id] = max(snap.t, float((config.starts or {}).get(agent.founder) or snap.t))
        # The House's tick: the broker's fills, the book's poll, the wakes and their batch, the expiry rules, the marks.
        self.broker.advance()
        book.poll()
        for row in self.ledger.iter(kinds=("book.fill",), after=self.fill_seq):
            self.fill_seq = row.seq
            checks["fills"] += 1
            order_id = str(row.payload.get("order_id") or "")
            order_snap = self.fill_snapshot.get(order_id)
            audit = audit_fill(row.payload, snap, self.submitted_at.get(order_id))
            spread = self.spread[row.seq] = spread_of_fill(row.payload, snap)
            self.fill_log.append({"agent": row.agent, "order_id": order_id, "side": row.payload.get("side"),
                                  "submitted_snapshot": order_snap, "filled_snapshot": snap.index, "at": row.at, "price": row.payload.get("price"),
                                  "audit": audit, "spread": spread})
            if order_snap is None or order_snap >= snap.index:
                checks["fills_not_on_newer_snapshot"] += 1
            if not audit.get("ok"):
                checks["fills_failing_audit"] += 1
        batch = []
        for agent in self.agents:
            if self.next_wake.get(agent.id, float("inf")) > clock():
                continue
            self.next_wake[agent.id] = clock() + agent.wake_minutes * 60
            tally = self.tallies[agent.id]
            tally.wakes += 1
            ctx = self.shim.snapshot(agent, book)
            ctx = json.loads(json.dumps(ctx, default=str))  # the box sees JSON, as the sandbox passes it
            checks["decisions"] += 1
            if self.source.current is None or self.source.current.t > clock() + 1e-9:
                checks["decision_snapshot_after_clock"] += 1
            self.decided_on.setdefault(agent.id, []).append((clock(), snap.index))
            try:
                answer = agent.decide(ctx)
                if not isinstance(answer, dict):
                    raise TypeError(f"decide returned {type(answer).__name__}")
                answer = json.loads(json.dumps(answer, default=str))
            except Exception as exc:  # noqa: BLE001 - a strategy's error is its wake's, as in its box
                tally.errors += 1
                tally.last_error = f"{type(exc).__name__}: {str(exc)[:300]} | {traceback.format_exc(limit=2)[-300:]}"
                continue
            self.shim._state["memory"][agent.id] = answer.get("memory") or {}
            thought = str(answer.get("thought") or "").strip()
            if thought:
                tally.thoughts.append((iso(clock()), thought[:600]))
                del tally.thoughts[:-config.keep_thoughts]
                tally.digests.append((iso(clock()), digest(thought)))
            for order_id in answer.get("cancels") or ():
                if isinstance(order_id, str):
                    book.cancel(agent.id, order_id)
            rows = [r for r in (answer.get("intents") or []) if isinstance(r, Mapping)]
            intents, dropped = self.shim._intents(agent, book, rows)
            tally.intents += len(rows)
            tally.dropped += dropped
            if rows:
                tally.decisions.append({"at": iso(clock()), "snapshot": snap.index, "asked": [
                    {k: r.get(k) for k in ("structure", "action", "quantity", "limit_price", "legs", "reason")} for r in rows]})
            batch += intents
        if batch:
            for outcome in book.submit(batch):
                if outcome.order_id:
                    self.fill_snapshot[str(outcome.order_id)] = snap.index
                    self.submitted_at[str(outcome.order_id)] = clock()
        self.shim._horizon_exits(book, float("inf"))
        for working in book.open_orders():
            self.fill_snapshot.setdefault(str(working.order_id), snap.index)
            self.submitted_at.setdefault(str(working.order_id), clock())
        if clock() - self.last_mark >= config.mark_every:
            book.mark()
            self.last_mark = clock()

    def finish(self) -> dict[str, Any]:
        if self.last is not None and self.started:
            self.book.mark()
        result = summarize(self)
        result["checks"]["fill_log"] = self.fill_log
        result["checks"]["decision_snapshots"] = {agent: [[iso(at), index] for at, index in rows] for agent, rows in self.decided_on.items()}
        result["run"] = {"label": self.config.label, "founders": len(self.agents), "start_after": self.config.start_after,
                         "starts": {k: iso(v) for k, v in (self.config.starts or {}).items() if v},
                         "reprice_from": None if self.config.reprice_from is None else
                         ("never" if self.config.reprice_from == float("inf") else iso(self.config.reprice_from)),
                         "zero_dte_greeks": bool(self.config.zero_dte_greeks)}
        return result

    def close(self) -> None:
        self.ledger.close()


def run_many(snapshots: str | Path, configs: Sequence[RunConfig], *, house_bars: str | Path | None, local_store: str | Path | None,
             work: str | Path | None = None, until: float | None = None, log: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    """Every floor in `configs` over ONE pass of the snapshot file (the file's parsing is most of a run's time).
    The floors share the market (`Market`) and nothing else. Returns each floor's result document (`summarize`),
    in order; `market` in each says what the pass's bars and features came from."""
    say = log or (lambda text: None)
    clock = SimClock()
    everyone = [load_founder(name) for name in sorted({name for config in configs for name in config.founders})]
    timeframes = sorted({str((a.needs.get("bars") or {}).get("timeframe") or "5Min") for a in everyone})
    market = Market(clock, house_bars=house_bars, local_store=local_store, symbols=founder_symbols(everyone), timeframes=timeframes)
    tmp = tempfile.TemporaryDirectory(prefix="forward-structures-", dir=work)
    floors: list[Floor] = []
    try:
        for n, config in enumerate(configs):
            floors.append(Floor(market, config, Path(tmp.name) / f"floor-{n}"))
        for snap in read_snapshots(snapshots, until=until):
            market.observe(snap)
            for floor in floors:
                floor.step(snap)
            if snap.index % 30 == 0:
                say(f"{iso(snap.t)} snapshot {snap.index}: {len(floors)} floors, fills {sum(f.checks['fills'] for f in floors)}")
        results = [floor.finish() for floor in floors]
        shared = {"bar_sources": market.bars.sources(), "bars_from_snapshot_mids": dict(sorted(market.bars.from_mids.items())),
                  "features_served": dict(market.features.served), "floors_in_the_pass": len(floors)}
        for result in results:
            result["market"] = shared
        return results
    finally:
        for floor in floors:
            floor.close()
        tmp.cleanup()


def run(snapshots: str | Path, *, house_bars: str | Path | None, local_store: str | Path | None, founders: Sequence[str] = FOUNDERS,
        work: str | Path | None = None, start: float | None = None, until: float | None = None, starts: Mapping[str, float] | None = None,
        mark_every: float = MARK_EVERY, keep_thoughts: int = 6, log: Callable[[str], None] | None = None,
        decide_override: Mapping[str, Callable[[dict], dict]] | None = None, reprice_from: float | None = None,
        zero_dte_greeks: bool = False, start_after: int = 0, require_spots: Sequence[str] | None = None,
        label: str = "forward") -> dict[str, Any]:
    """The forward test of one floor (`RunConfig` says what each argument does); `until` bounds the simulated
    session (epoch seconds). Returns the result document (`summarize`)."""
    config = RunConfig(label=label, founders=founders, start=start, start_after=start_after, starts=starts, reprice_from=reprice_from,
                       zero_dte_greeks=zero_dte_greeks, decide_override=decide_override, keep_thoughts=keep_thoughts,
                       mark_every=mark_every, require_spots=require_spots)
    return run_many(snapshots, [config], house_bars=house_bars, local_store=local_store, work=work, until=until, log=log)[0]


def audit_fill(payload: Mapping[str, Any], snap: Snapshot, submitted: float | None) -> dict[str, Any]:
    """A fill checked against the raw snapshot it was made on, apart from the broker's code: the structure's touch from
    its legs' recorded quotes (an open at the ask: long legs' asks less short legs' bids; a close at the bid: long
    legs' bids less short legs' asks, a long leg with no bid at nothing), every leg quoted AFTER the order was accepted,
    and every sized leg showing at least ten times the contracts taken (the 10% rule's floor)."""
    try:
        spec = core.spec_of_code(str((payload.get("instrument") or {}).get("market_id")))
    except ValueError as exc:
        return {"ok": False, "why": f"not a structure: {exc}"}
    buy = payload.get("side") == "buy"
    quantity = Decimal(str(payload.get("quantity")))
    touches, times, short = {}, [], []
    for leg in spec.legs:
        row = snap.rows.get(leg.occ) or {}
        bid = Decimal(str(row["bid"])) if row.get("bid") not in (None, 0, 0.0) else None
        ask = Decimal(str(row["ask"])) if row.get("ask") not in (None, 0, 0.0) else None
        free = not buy and leg.sign > 0 and bid is None and ask is not None
        touches[leg.occ] = (Decimal(0) if free else bid, ask)
        times.append(parse_ts(row.get("as_of")) if row.get("as_of") else None)
        if not free:
            takes_ask = (leg.sign > 0) == buy
            size = row.get("ask_size" if takes_ask else "bid_size")
            if size is None or Decimal(str(size)) < 10 * quantity * leg.ratio:
                short.append(leg.occ)
    bid, ask = core.quote(spec, touches)
    touch = ask if buy else bid
    price = Decimal(str(payload.get("price")))
    newer = submitted is not None and all(t is not None and t > submitted for t in times)
    ok = touch is not None and touch == price and newer and not short
    return {"ok": ok, "touch": None if touch is None else str(touch), "legs_newer_than_acceptance": newer, "legs_short_of_size": short}


def spread_of_fill(payload: Mapping[str, Any], snap: Snapshot) -> dict[str, Any]:
    """What a fill paid for crossing the structure's bid-ask, on the snapshot it was made on (scoreboard metric 4,
    "the bid-ask paid, a share of premium or net debit"): the structure's mid from its legs' recorded quotes (a leg
    with no bid at half its ask), the fill's distance from it (a buy above, a sale under) times the multiplier and
    the contracts, and that as a share of the premium (the structure's natural price at the fill, times the same:
    the debit paid, the credit taken, the value sold or the cost to buy back). Empty for a fill that is not a
    structure's; `mid` None where a leg has no ask."""
    try:
        spec = core.spec_of_code(str((payload.get("instrument") or {}).get("market_id")))
    except ValueError:
        return {}
    mid = Decimal(spec.collateral)
    for leg in spec.legs:
        row = snap.rows.get(leg.occ) or {}
        if row.get("ask") in (None, 0, 0.0):
            return {"mid": None}
        mid += leg.sign * leg.ratio * (Decimal(str(row.get("bid") or 0)) + Decimal(str(row["ask"]))) / 2
    price = Decimal(str(payload.get("price")))
    size = Decimal(str(payload.get("quantity"))) * Decimal(str((payload.get("instrument") or {}).get("multiplier") or 100))
    paid = ((price - mid) if payload.get("side") == "buy" else (mid - price)) * size
    premium = abs(core.natural_price(spec, price)) * size
    return {"mid": float(round(mid, 4)), "spread_paid_usd": float(round(paid, 2)), "premium_usd": float(round(premium, 2)),
            "spread_share_of_premium": None if premium <= 0 else float(round(paid / premium, 4))}


def _median(values: Sequence[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    n = len(ordered)
    return round(ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2, 4)


def _money(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def summarize(floor: Floor) -> dict[str, Any]:
    """Per founder: its wakes, intents, House refusals and drops, book refusals, opens and closes (every fill, at
    held and natural prices, with the bid-ask it paid against the structure's mid), realized P&L after fees, what it
    still holds at the last snapshot with its mark (the structure's bid) and unrealized P&L, its latest thoughts and
    a digest of every wake's thought (`runs_of`)."""
    book, broker, ledger, shim, last = floor.book, floor.broker, floor.ledger, floor.shim, floor.last
    fills = [row for row in ledger.iter(kinds=("book.fill",))]
    refused = [row for row in ledger.iter(kinds=("book.refused",))]
    out = []
    for agent in floor.agents:
        account = book.account(agent.id)
        mine = [row for row in fills if row.agent == agent.id]
        trades = []
        for row in mine:
            p = row.payload
            inst = p.get("instrument") or {}
            spec = core.spec_of_code(str(inst.get("market_id")), venue=BOOK) if inst.get("market_id") else None
            price = Decimal(str(p["price"]))
            natural = None if spec is None else float(core.natural_price(spec, price))
            spread = floor.spread.get(row.seq) or {}
            trades.append({"at": row.at, "side": p.get("side"), "action": "open" if p.get("side") == "buy" else "close",
                           "structure": spec.type if spec else None, "market_id": inst.get("market_id"), "quantity": float(Decimal(str(p["quantity"]))),
                           "held_price": float(price), "natural_price": natural, "fee_usd": _money(p.get("fee_usd") or 0),
                           "realized_usd": _money(p["realized"]) if p.get("realized") is not None and p.get("side") == "sell" else None,
                           "flat": bool(p.get("flat")), "mid": spread.get("mid"), "spread_paid_usd": spread.get("spread_paid_usd"),
                           "spread_share_of_premium": spread.get("spread_share_of_premium"), "reason": str(p.get("reason") or "")[:240]})
        held = []
        for holding in account.holdings.values():
            inst = holding.instrument
            mark = book.marks.get(inst.key)
            spec = structures.spec_of(inst)
            row = {"market_id": inst.market_id, "structure": spec.type, "quantity": float(holding.quantity),
                   "held_cost": float(holding.average_cost), "mark": None if mark is None else float(mark),
                   "unrealized_usd": None if mark is None else _money((mark - holding.average_cost) * inst.multiplier * holding.quantity),
                   "expiry": spec.expiry}
            if last is not None and spec.type not in structures.TWO_EXPIRIES and spec.expiry <= datetime.fromtimestamp(last.t, NEW_YORK).strftime("%Y-%m-%d"):
                # held past its expiry day's close: the broker settles it at intrinsic on the underlying's close
                touch = last.spot.get(spec.underlying)
                if touch:
                    value = structures.intrinsic(spec, Decimal(str(round((touch[0] + touch[1]) / 2, 4))))
                    row["intrinsic_at_last_spot"] = float(value)
            held.append(row)
        tally = floor.tallies[agent.id]
        reasons: dict[str, int] = {}
        for row in refused:
            if row.agent == agent.id:
                for reason in row.payload.get("reasons") or ["?"]:
                    reasons[str(reason)[:160]] = reasons.get(str(reason)[:160], 0) + 1
        closes = [t for t in trades if t["action"] == "close" and t["flat"]]
        closed_ids = {t["market_id"] for t in closes}
        on_closed = sum(t["spread_paid_usd"] or 0 for t in trades if t["market_id"] in closed_ids)
        realized_closed = sum(t["realized_usd"] or 0 for t in closes)
        out.append({
            "founder": agent.founder, "seed": agent.seed, "wake_minutes": agent.wake_minutes, "wakes": tally.wakes, "decide_errors": tally.errors,
            "last_error": tally.last_error, "intents_asked": tally.intents, "dropped": tally.dropped[:10], "refusals": reasons,
            "limits_repriced_by_the_house": shim.repriced.get(agent.id, 0),
            "opens": sum(1 for t in trades if t["action"] == "open"), "closes": sum(1 for t in trades if t["action"] == "close"),
            "closed_structures": len(closes), "realized_usd": _money(account.realized), "fees_usd": _money(account.fees),
            "closed_realized_usd": [t["realized_usd"] for t in closes],
            "spread_paid_usd": round(sum(t["spread_paid_usd"] or 0 for t in trades), 2),
            "spread_share_of_premium_median": _median([t["spread_share_of_premium"] for t in trades if t["spread_share_of_premium"] is not None]),
            "spread_paid_on_closed_usd": round(on_closed, 2),
            "spread_share_of_closed_net": round(on_closed / realized_closed, 4) if realized_closed > 0 else None,
            "equity_usd": _money(book.equity(agent.id)), "stake_usd": float(STAKE), "held_at_end": held, "fills": trades,
            "decisions_with_intents": tally.decisions[:40], "last_thoughts": tally.thoughts, "thought_runs": runs_of(tally.digests),
        })
    orders = [order for order in broker._orders.values()]
    statuses: dict[str, int] = {}
    for order in orders:
        statuses[order.status] = statuses.get(order.status, 0) + 1
    every = [t for f in out for t in f["fills"]]
    realized_closed = sum(r or 0 for f in out for r in f["closed_realized_usd"])
    on_closed = sum(f["spread_paid_on_closed_usd"] for f in out)
    return {"founders": out,
            "desk": {"closed_structures": sum(f["closed_structures"] for f in out), "realized_usd": _money(sum(Decimal(str(f["realized_usd"])) for f in out)),
                     "agents_positive_on_2_closed": sum(1 for f in out if f["closed_structures"] >= 2 and f["realized_usd"] > 0),
                     "held_at_end": sum(len(f["held_at_end"]) for f in out),
                     "unrealized_usd_at_end": _money(sum(Decimal(str(h["unrealized_usd"] or 0)) for f in out for h in f["held_at_end"])),
                     "spread_paid_usd": round(sum(t["spread_paid_usd"] or 0 for t in every), 2),
                     "metric_4_spread_share_of_premium_median": _median([t["spread_share_of_premium"] for t in every if t["spread_share_of_premium"] is not None]),
                     "spread_shares_of_premium": sorted(t["spread_share_of_premium"] for t in every if t["spread_share_of_premium"] is not None),
                     "spread_paid_on_closed_usd": round(on_closed, 2),
                     "spread_share_of_closed_net": round(on_closed / realized_closed, 4) if realized_closed > 0 else None},
            "broker": {"orders": len(orders), "statuses": statuses, "fills": len(broker._fills)},
            "checks": {**floor.checks, "leg_reads": len(floor.source.served)},
            "alerts": shim.alerts[-40:]}


# ------------------------------------------------------------------------------------------ the live House's day
DAY = "2026-09-25"


def day_window(day: str) -> tuple[float, float]:
    """The day's read window in epoch seconds: 09:00 to 16:05 New York (the session and its opening minutes' data)."""
    from datetime import date as _date, time as _time

    moment = _date.fromisoformat(day)
    begin = datetime.combine(moment, _time(9, 0), NEW_YORK).timestamp()
    end = datetime.combine(moment, _time(16, 5), NEW_YORK).timestamp()
    return begin, end


def _fill(template: str, **values: Any) -> str:
    for key, value in values.items():
        template = template.replace(f"__{key.upper()}__", repr(value))
    return template


#: The read-only queries the forward test's inputs come from, run on the House box through the session's `rx.py`
#: (sqlite `mode=ro`; no order, no write), filled in for a day by `bars_query`, `live_query`, `chains_query`.
BARS_QUERY = r'''# READ-ONLY (sqlite mode=ro): the underlying bars and features the House showed the day's structure founders, as it
# recorded them (recordings.sqlite, `House._cached`), the earliest and the latest recording of each key in the day's
# window; and the options feature rows available from noon UTC the day before for the founders' symbols. No order, no write.
import gzip, json, sqlite3, sys, time
keys = sys.argv[1].split(";")
since, until, features_from, symbols = __SINCE__, __UNTIL__, __FEATURES_FROM__, __SYMBOLS__
db = sqlite3.connect('file:/workspace/state/recordings.sqlite?mode=ro', uri=True)
out = {"bars": {}, "features": []}
for key in keys:
    got = {}
    for label, order in (("earliest", "ASC"), ("latest", "DESC")):
        row = db.execute(f"SELECT received, payload FROM snapshots WHERE source = ? AND received >= ? AND received <= ? ORDER BY received {order} LIMIT 1",
                         (key, since, until)).fetchone()
        if row:
            got[label] = {"received": row[0], "value": json.loads(gzip.decompress(row[1]))}
    out["bars"][key] = got
oh = sqlite3.connect('file:/workspace/state/options_history.sqlite?mode=ro', uri=True)
marks = ",".join("?" * len(symbols))
for r in oh.execute(f"SELECT symbol, day, version, available_at, payload FROM features WHERE available_at >= ? AND symbol IN ({marks})", (features_from, *symbols)):
    out["features"].append({"symbol": r[0], "day": r[1], "version": r[2], "available_at": r[3], "payload": json.loads(r[4])})
print(json.dumps(out, separators=(",", ":")))
'''
LIVE_QUERY = r'''# READ-ONLY (sqlite mode=ro): what the live structure founders (every agent born of one of the forward test's
# founders, alive in the day's window) did on the day: birth (founder, family, code sha), strategy changes, wakes,
# intents, House/book refusals, fills, the latest mark, and EVERY thought. No order, no write.
import json, sqlite3
since, until, founders = __SINCE__, __UNTIL__, set(__FOUNDERS__)
db = sqlite3.connect('file:/workspace/state/ledger.sqlite?mode=ro', uri=True)
born = {}
for at, agent, payload in db.execute("SELECT at, agent, payload FROM ledger WHERE kind = 'agent.born' ORDER BY seq"):
    p = json.loads(payload)
    if p.get("founder") in founders and at <= until and agent not in born:
        born[agent] = {"at": at, "founder": p.get("founder"), "family": p.get("family"), "code_sha256": p.get("code_sha256"), "style": p.get("style")}
agents = sorted(born)
out = {a: {"born": born[a], "strategy": [], "woke": [], "intents": [], "refused": [], "fills": [], "orders": [], "mark": None, "thoughts": []} for a in agents}
marks = ",".join("?" * len(agents))
kinds = ('agent.strategy', 'agent.woke', 'agent.intent', 'book.refused', 'book.fill', 'book.order', 'book.mark', 'agent.thought')
rows = db.execute(f"SELECT at, kind, agent, payload FROM ledger WHERE agent IN ({marks}) AND kind IN ({','.join('?' * len(kinds))}) "
                  "AND at >= ? AND at <= ? ORDER BY seq", (*agents, *kinds, since, until)) if agents else []
for at, kind, agent, payload in rows:
    p = json.loads(payload)
    row = out[agent]
    if kind == "agent.strategy":
        row["strategy"].append({"at": at, "code_sha256": p.get("code_sha256"), "note": str(p.get("note") or p.get("reason") or "")[:200],
                                "control": p.get("control"), "family": p.get("family")})
    elif kind == "agent.woke":
        row["woke"].append([at, p.get("ok"), p.get("intents"), p.get("book"), (p.get("dropped") or [])[:2]])
    elif kind == "agent.intent":
        inst = p.get("instrument") or {}
        row["intents"].append({"at": at, "book": p.get("book"), "market_id": inst.get("market_id"), "side": p.get("side"), "quantity": p.get("quantity"),
                               "limit_price": p.get("limit_price"), "reason": str(p.get("reason") or "")[:200], "id": p.get("id")})
    elif kind == "book.refused":
        row["refused"].append({"at": at, "reasons": p.get("reasons"), "market_id": (p.get("instrument") or {}).get("market_id")})
    elif kind == "book.fill":
        inst = p.get("instrument") or {}
        row["fills"].append({"at": at, "book": p.get("book"), "market_id": inst.get("market_id"), "side": p.get("side"), "quantity": p.get("quantity"),
                             "price": p.get("price"), "fee_usd": p.get("fee_usd"), "realized": p.get("realized"), "flat": p.get("flat"),
                             "reason": str(p.get("reason") or "")[:160], "intent_id": p.get("intent_id")})
    elif kind == "book.order":
        row["orders"].append({"at": at, "status": p.get("status"), "market_id": (p.get("instrument") or {}).get("market_id"), "side": p.get("side"),
                              "reason": str(p.get("reason") or "")[:160]})
    elif kind == "book.mark" and p.get("book") == "options-shadow":
        row["mark"] = {"at": at, "equity": p.get("equity"), "cash": p.get("cash"), "realized": p.get("realized"), "fees": p.get("fees"), "holdings": p.get("holdings")}
    elif kind == "agent.thought":
        row["thoughts"].append([at, str(p.get("text") or "")[:400]])
print(json.dumps({a: r for a, r in out.items() if r["woke"]}, separators=(",", ":")))
'''
CHAINS_QUERY = r'''# READ-ONLY (sqlite mode=ro): every structure chain the House showed its structure agents in the day's window, as it
# recorded them (recordings.sqlite, `House._cached` "structure-chain:..." keys), a row as [occ, bid, ask, iv, delta,
# as_of, spot]. No order, no write.
import gzip, json, sqlite3
since, until = __SINCE__, __UNTIL__
db = sqlite3.connect('file:/workspace/state/recordings.sqlite?mode=ro', uri=True)
out = []
for source, started, received, payload in db.execute(
        "SELECT source, started, received, payload FROM snapshots WHERE received >= ? AND received <= ? AND source LIKE 'structure-chain:%' "
        "ORDER BY received", (since, until)):
    rows = json.loads(gzip.decompress(payload))
    out.append({"source": source, "started": started, "received": received,
                "rows": [[r.get("occ") or r.get("symbol"), r.get("bid"), r.get("ask"), r.get("iv"), r.get("delta"), r.get("as_of"), r.get("underlying_price")]
                         for r in rows if isinstance(r, dict)]})
print(json.dumps(out, separators=(",", ":")))
'''


def bars_query(day: str = DAY, founders: Sequence[str] = FOUNDERS) -> str:
    begin, end = day_window(day)
    from datetime import date as _date, timedelta as _timedelta

    before = (_date.fromisoformat(day) - _timedelta(days=1)).isoformat()
    return _fill(BARS_QUERY, since=begin, until=end, features_from=f"{before}T12:00:00Z",
                 symbols=founder_symbols([load_founder(name) for name in founders]))


def live_query(day: str = DAY, founders: Sequence[str] = FOUNDERS) -> str:
    begin, end = day_window(day)
    return _fill(LIVE_QUERY, since=_sec(begin), until=_sec(end), founders=sorted({load_founder(name).founder for name in founders}))


def chains_query(day: str = DAY) -> str:
    begin, end = day_window(day)
    return _fill(CHAINS_QUERY, since=begin, until=end)


def bar_keys(founders: Sequence[str] = FOUNDERS) -> str:
    """The `House._cached` keys of the founders' bars (`House.snapshot`), for BARS_QUERY."""
    keys = set()
    for name in founders:
        needs = load_founder(name).needs
        bars = dict(needs.get("bars") or {})
        symbols = [str(s) for s in (needs.get("symbols") or [])][:12]
        keys.add(f"bars:{','.join(symbols)}:{bars.get('timeframe') or '5Min'}:{max(1, min(int(bars.get('limit') or 120), 500))}")
    return ";".join(sorted(keys))


def live_summary(live: Mapping[str, Any], *, since: str = "") -> dict[str, dict[str, Any]]:
    """What each live structure founder did (LIVE_QUERY's rows), by its founder: its agent, birth, first wake, wakes,
    intents, the House's and the book's refusals, its fills on options-shadow (opens, closes, realized after fees), the
    structures it still held at the last row, strategy changes (a rewrite, a pause), its latest thought and a digest of
    every thought (`runs_of`). Where several agents alive that day descend from one founder, the one born first is
    the founder's row and the others are named under `others`."""
    out: dict[str, dict[str, Any]] = {}
    for agent, row in sorted(live.items(), key=lambda pair: str((pair[1].get("born") or {}).get("at") or "")):
        founder = (row.get("born") or {}).get("founder") or (row.get("born") or {}).get("family")
        if not founder:
            continue
        if founder in out:
            out[founder]["others"].append(agent)
            continue
        woke = [w for w in row.get("woke") or [] if w[0] >= since]
        fills = [f for f in row.get("fills") or [] if f.get("book") == BOOK and f["at"] >= since]
        held: dict[str, float] = {}
        for f in fills:
            held[f["market_id"]] = held.get(f["market_id"], 0.0) + (1 if f["side"] == "buy" else -1) * float(f["quantity"])
        reasons: dict[str, int] = {}
        for r in row.get("refused") or []:
            if r["at"] >= since:
                for reason in r.get("reasons") or ["?"]:
                    reasons[str(reason)[:160]] = reasons.get(str(reason)[:160], 0) + 1
        closes = [f for f in fills if f["side"] == "sell"]
        thoughts = [t for t in row.get("thoughts") or [] if t[0] >= since]
        out[founder] = {"agent": agent, "born": (row.get("born") or {}).get("at"), "first_wake_today": woke[0][0] if woke else None,
                        "wakes": len(woke), "intents": sum(1 for i in row.get("intents") or [] if i["at"] >= since and i.get("book") == BOOK),
                        "refusals": reasons, "opens": sum(1 for f in fills if f["side"] == "buy"), "closes": len(closes),
                        "closed_structures": sum(1 for f in closes if f.get("flat")),
                        "realized_usd": round(sum(float(f["realized"]) for f in closes if f.get("realized") is not None), 2),
                        "fees_usd": round(sum(float(f.get("fee_usd") or 0) for f in fills), 2),
                        "fills": [{k: f.get(k) for k in ("at", "side", "market_id", "quantity", "price", "fee_usd", "realized", "flat", "reason")} for f in fills],
                        "held_at_end": [code for code, q in held.items() if q > 0],
                        "strategy_changes": [{k: c.get(k) for k in ("at", "control", "code_sha256", "note")} for c in row.get("strategy") or []],
                        "last_mark": row.get("mark"), "last_thought": (thoughts or [[None, None]])[-1],
                        "thought_runs": runs_of([(at, digest(text)) for at, text in thoughts]), "others": [],
                        "thought_digests": [[at, digest(text)] for at, text in thoughts]}
    return out


def thought_agreement(forward: Mapping[str, Any] | None, live: Mapping[str, Mapping[str, Any]], *, wake_minutes: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Whether the forward twin gave the live founder's reasons at the same minutes. Each live thought of the
    founder's OWN code (before its first strategy change: a rewrite or a pause) against the forward thoughts within
    one wake interval of it, both digested (`digest`: the numbers out). Per founder: the live thoughts compared, how
    many had a forward thought that near, how many of those said the same, and the first three that did not."""
    twins = {f["founder"]: f for f in (forward or {}).get("founders") or []}
    out: dict[str, Any] = {}
    for founder, mine in sorted(live.items()):
        twin = twins.get(founder)
        if twin is None:
            continue
        tolerance = 60.0 * float((wake_minutes or {}).get(founder) or twin.get("wake_minutes") or 10)
        cut = min((str(c.get("at")) for c in mine.get("strategy_changes") or []), default="9999")
        runs = [(parse_ts(first), parse_ts(last), text) for first, last, _, text in twin.get("thought_runs") or []]
        compared = near = same = 0
        differ = []
        for at, text in mine.get("thought_digests") or []:
            moment = parse_ts(at)
            if at >= cut or moment is None:
                continue
            compared += 1
            close = [said for begin, end, said in runs if begin - tolerance <= moment <= end + tolerance]
            if close:
                near += 1
                if text in close:
                    same += 1
                elif len(differ) < 3:
                    differ.append({"live_at": at, "live": text, "forward_near": close[:2]})
        out[founder] = {"live_thoughts_compared": compared, "with_a_forward_thought_near": near, "same_digest": same,
                        "share_same": round(same / near, 3) if near else None, "cut_at_first_strategy_change": None if cut == "9999" else cut,
                        "first_differences": differ}
    return out


def compare(session: Mapping[str, Any], from_birth: Mapping[str, Any] | None, live: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row a founder: the forward test over the recorded session (all founders on one floor, the first start),
    the forward test from the live founder's first wake, and the live founder."""
    def brief(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {"wakes": row["wakes"], "opens": row["opens"], "closes": row["closes"], "closed_structures": row["closed_structures"],
                "realized_usd": row["realized_usd"], "held_at_end": [h["market_id"] for h in row["held_at_end"]],
                "unrealized_usd": round(sum(h["unrealized_usd"] or 0 for h in row["held_at_end"]), 2), "refusals": sum(row["refusals"].values())}
    by = lambda result: {f["founder"]: f for f in (result or {}).get("founders") or []}  # noqa: E731
    a, b = by(session), by(from_birth)
    out = []
    for founder in sorted(set(a) | set(live)):
        mine = live.get(founder)
        out.append({"founder": founder, "forward_recorded_session": brief(a.get(founder)), "forward_from_birth": brief(b.get(founder)),
                    "live": None if mine is None else {k: mine[k] for k in ("agent", "first_wake_today", "wakes", "intents", "opens", "closes",
                                                                             "closed_structures", "realized_usd", "held_at_end", "refusals",
                                                                             "strategy_changes", "others")}})
    return out


def compare_chains(snapshots: str | Path, house_chains: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The chain the forward test shows against the chains the live House showed (CHAINS_QUERY): each recorded chain
    against the last snapshot before the House finished reading it. Per row the House showed: whether the recording
    holds the contract at all (the recorder's 4% and 12% bands against the chain's 20%), the difference of the mids
    (the two reads are up to a minute apart), and of the greeks (Alpaca's against the forward test's Black-Scholes) on
    contracts of 1 day or more ONLY: Alpaca gives no greeks on a contract expiring today, so nothing here validates a
    same-day Black-Scholes delta (`*_0dte_rows_forward_delta_computable` only counts where one could be solved).
    `*_rows_delta_missing_house_only`: rows of 1 day or more the House showed WITHOUT a delta that the forward chain
    carries one for (a founder that keeps only rows with a delta could pick one forward and not live);
    `*_rows_delta_missing_forward_only` the reverse; `*_rows_delta_missing_both`."""
    chains = sorted(house_chains, key=lambda c: float(c.get("received") or 0))
    stats: dict[str, dict[str, list[float]]] = {}
    counts: dict[str, int] = {}

    def add(kind: str, key: str, value: float) -> None:
        stats.setdefault(kind, {}).setdefault(key, []).append(value)

    def count(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def against(chain: Mapping[str, Any], snap: Snapshot) -> None:
        count("chains")
        today = datetime.fromtimestamp(snap.t, NEW_YORK).strftime("%Y-%m-%d")
        for occ, bid, ask, iv, delta, as_of, spot in chain.get("rows") or ():
            kind = "etf" if str(occ)[:-15] in ("SPY", "QQQ", "IWM") else "stock"
            count(f"{kind}_rows")
            row = snap.rows.get(str(occ))
            if row is None or row.get("bid") is None or row.get("ask") is None:
                count(f"{kind}_rows_not_recorded")
                continue
            add(kind, "abs_mid_difference", abs((float(row["bid"]) + float(row["ask"])) / 2 - (float(bid) + float(ask)) / 2))
            zero = "20" + str(occ)[-15:-9] == today.replace("-", "")
            touch = snap.spot.get(str(occ)[:-15])
            mine = greeks(row, (touch[0] + touch[1]) / 2 if touch else None, snap.t)
            if zero:
                count(f"{kind}_0dte_rows")
                if delta is None:
                    count(f"{kind}_0dte_rows_house_no_delta")
                if mine[1] is not None:
                    count(f"{kind}_0dte_rows_forward_delta_computable")
                continue
            if delta is None or mine[1] is None:
                count(f"{kind}_rows_delta_missing_" + ("both" if delta is None and mine[1] is None else "house_only" if delta is None else "forward_only"))
                continue
            add(kind, "abs_delta_difference", abs(float(delta) - mine[1]))
            if iv is not None and mine[0] is not None:
                add(kind, "abs_iv_difference", abs(float(iv) - mine[0]))

    i, previous = 0, None
    for snap in read_snapshots(snapshots):
        while i < len(chains) and float(chains[i]["received"]) < snap.t:
            if previous is not None:
                against(chains[i], previous)
            else:
                count("chains_before_the_first_snapshot")
            i += 1
        previous = snap
    while i < len(chains) and previous is not None:
        against(chains[i], previous)
        i += 1

    def q(values: list[float], p: float) -> float | None:
        ordered = sorted(values)
        return round(ordered[min(len(ordered) - 1, int(p * (len(ordered) - 1)))], 4) if ordered else None

    summary = {kind: {key: {"n": len(v), "median": q(v, 0.5), "p90": q(v, 0.9), "share_over_0.05": round(sum(1 for x in v if x > 0.05) / len(v), 4)}
                      for key, v in keys.items()} for kind, keys in stats.items()}
    return {"counts": counts, "differences": summary}


# ------------------------------------------------------------------------------------------ the calibration refit
def load_fit(path: str | Path | None) -> Any:
    """The module holding `fit_spread_calibration` and `CALIBRATED_SPREADS`: `league.options_history` once
    `s3/calibration` is merged, else that branch's file (`git show origin/s3/calibration:league/options_history.py`),
    loaded as it is: standard library only."""
    import league.options_history as main_history

    if path is None and hasattr(main_history, "fit_spread_calibration"):
        return main_history
    if path is None:
        raise SystemExit("league.options_history has no fit_spread_calibration on this branch: pass --fit-from (s3/calibration's file)")
    spec = importlib.util.spec_from_file_location("s3_options_history", Path(path).expanduser())
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _sec(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_calibration_store(snapshots: str | Path, store_path: str | Path, fit: Any, *, local_store: str | Path | None) -> dict[str, Any]:
    """A scratch options-history store (the House's SCHEMA) holding the day's recorded quotes and the 15-minute
    bars of its contracts built from the snapshots, plus (with `local_store`) the local copy's recorded quotes of
    Sept 22-24 and their contracts' 15-minute bars: what `fit_spread_calibration` reads.

    The day's bars, close-stamped as the store keeps them: each contract's minute bars (`mbar`, the most complete
    reading of each minute: the one with the largest volume) grouped into 15-minute windows the recorder saw whole
    (from the first snapshot to the last); o the first minute's open, h and l the extremes, c the last minute's
    close, v the minutes' volumes summed, and n the trades SEEN (distinct latest-trade times) or the minutes with
    volume, the larger. v and n are lower bounds (a snapshot a minute sees the latest minute bar and the latest trade
    only), so a window can fail the tape's liquidity rule (5 contracts in 2 trades) that the real bar passed: fewer
    pairs, never a looser one. A quote is kept once a contract and second (the store's key), two-sided (0 < bid < ask)."""
    store = fit.OptionsHistory(store_path)
    db = store.db
    minutes: dict[tuple[str, int], tuple[float, float, float, float, float]] = {}
    trades: dict[str, set[float]] = {}
    spots: dict[str, list[tuple[float, float]]] = {}
    first = last = None
    quotes = 0
    for snap in read_snapshots(snapshots):
        if snap.version < 2:
            continue
        first = snap.at if first is None else first
        last = snap.at
        for symbol, (bid, ask) in snap.spot.items():
            spots.setdefault(symbol, []).append((snap.at, (bid + ask) / 2))
        batch = []
        for occ, row in snap.rows.items():
            bid, ask, as_of = row.get("bid"), row.get("ask"), row.get("as_of")
            if bid is not None and ask is not None and as_of and 0 < float(bid) < float(ask):
                batch.append((occ, as_of[:19] + "Z", float(bid), float(ask), "recorded snapshot (forward_structures)"))
            if row.get("last_t") and row.get("last") is not None:
                moment = parse_ts(row["last_t"])
                if moment is not None:
                    trades.setdefault(occ, set()).add(moment)
            bar = row.get("mbar") or {}
            begun = parse_ts(bar.get("t")) if bar.get("t") else None
            if begun is not None and bar.get("c") is not None:
                key = (occ, int(begun))
                volume = float(bar.get("v") or 0)
                if key not in minutes or volume >= minutes[key][4]:
                    minutes[key] = (float(bar["o"]), float(bar["h"]), float(bar["l"]), float(bar["c"]), volume)
        db.executemany("INSERT OR IGNORE INTO quotes (occ, t, bid, ask, source) VALUES (?, ?, ?, ?, ?)", batch)
        quotes += len(batch)
    windows: dict[tuple[str, int], list[tuple[int, tuple]]] = {}
    for (occ, begun), bar in minutes.items():
        start = begun - begun % 900
        if first is None or start < first or start + 900 > (last or 0) + 60:
            continue  # a window the recorder did not see whole
        windows.setdefault((occ, start), []).append((begun, bar))
    rows = []
    for (occ, start), members in windows.items():
        members.sort()
        seen = sum(1 for t in trades.get(occ, ()) if start <= t < start + 900)
        n = max(seen, sum(1 for _, bar in members if bar[4] > 0))
        rows.append((occ, "15Min", _sec(start + 900), members[0][1][0], max(b[1] for _, b in members), min(b[2] for _, b in members),
                     members[-1][1][3], sum(b[4] for _, b in members), n, None))
    db.executemany("INSERT OR IGNORE INTO bars (occ, timeframe, t, o, h, l, c, v, n, vw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.commit()
    copied = {}
    if local_store:  # read through its own read-only connection: the local copy is never written
        local = sqlite3.connect(f"file:{Path(local_store).expanduser()}?mode=ro", uri=True)
        try:
            recorded = local.execute("SELECT occ, t, bid, ask, source FROM quotes").fetchall()
            db.executemany("INSERT OR IGNORE INTO quotes (occ, t, bid, ask, source) VALUES (?, ?, ?, ?, ?)", recorded)
            names = sorted({row[0] for row in recorded})
            count = 0
            for i in range(0, len(names), 400):
                group = names[i:i + 400]
                found = local.execute(f"SELECT occ, timeframe, t, o, h, l, c, v, n, vw FROM bars WHERE timeframe = '15Min' AND t >= '2026-09-15' "
                                      f"AND occ IN ({','.join('?' * len(group))})", group).fetchall()
                db.executemany("INSERT OR IGNORE INTO bars (occ, timeframe, t, o, h, l, c, v, n, vw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", found)
                count += len(found)
            copied = {"quotes": len(recorded), "bars": count}
            db.commit()
        finally:
            local.close()
    return {"store": store, "spots": spots, "quotes_read": quotes, "bars_built": len(rows), "first": _sec(first) if first else None,
            "last": _sec(last) if last else None, "copied_from_local": copied}


def stored_underlier_read_only(local_store: str | Path) -> Callable[[str, str, str, str], list[dict[str, Any]]]:
    """`options_history.stored_underlier` over a READ-ONLY connection (`?mode=ro`): the local copy's `underlier_bars`
    (a bar whose close is in [start, end]). Reviewed Sept 25: building `OptionsHistory` on the shared copy runs its
    SCHEMA and a commit there, and a fit module with a newer SCHEMA (`--fit-from`) would write into the copy every
    other run's replays read."""
    path = Path(local_store).expanduser()

    def underlier_bars(symbol: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        begin, finish = parse_ts(start) if start else None, parse_ts(end) if end else None
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT payload FROM underlier_bars WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                              (symbol.upper(), timeframe, 0.0 if begin is None else begin, 1e18 if finish is None else finish))
            return [json.loads(payload) for (payload,) in rows]
        finally:
            db.close()

    return underlier_bars


def _underlier(fit: Any, local_store: str | Path | None, spots: Mapping[str, Sequence[tuple[float, float]]]) -> Callable[..., list[dict[str, Any]]]:
    """`underlier_bars(symbol, "15Min", start, end)` for the fit's moneyness: the local copy's bars through Sept 24
    (read-only: `stored_underlier_read_only`), then the day's 15-minute closes of the snapshots' mids (close-stamped).
    `fit` is not asked for a store."""
    stored = stored_underlier_read_only(local_store) if local_store else None
    built: dict[str, list[dict[str, Any]]] = {}
    for symbol, points in spots.items():
        closes: dict[int, float] = {}
        for t, mid in points:
            closes[int(t - t % 900) + 900] = mid
        built[symbol] = [{"t": _sec(t), "c": c} for t, c in sorted(closes.items())]

    def underlier_bars(symbol: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        rows = list(stored(symbol, timeframe, start, end) if stored else [])
        after = rows[-1]["t"] if rows else ""
        rows += [bar for bar in built.get(symbol, []) if bar["t"] > after and start <= bar["t"] <= end]
        return rows

    return underlier_bars


def calibration_pairs(fit: Any, store: Any, underlier: Callable[..., list[dict[str, Any]]], *, start: str, end: str,
                      max_gap: float = 300.0) -> list[dict[str, Any]]:
    """The pairs `fit_spread_calibration` fits on (its own pairing, restated so a table can be judged on them): each
    recorded quote with its contract's last qualifying 15-minute bar closed at most `max_gap` seconds before it."""
    import bisect as _bisect

    live = dict(fit.LIQUIDITY)
    quotes: dict[str, list[tuple[str, float, float]]] = {}
    for occ, t, bid, ask in store.db.execute("SELECT occ, t, bid, ask FROM quotes WHERE t >= ? AND t <= ? ORDER BY occ, t", (start, end)):
        quotes.setdefault(occ, []).append((t, float(bid), float(ask)))
    if not quotes:
        return []
    first = min(rows[0][0] for rows in quotes.values())
    last_t = max(rows[-1][0] for rows in quotes.values())
    bars_from = fit.iso(fit._ts(first) - 7 * 86400)
    spots = {}
    for root in sorted({occ[:-15] for occ in quotes}):
        rows = underlier(root, "15Min", bars_from, last_t) or []
        spots[root] = ([fit._ts(r["t"]) for r in rows], [float(r["c"]) for r in rows])
    pairs = []
    names = list(quotes)
    for i in range(0, len(names), 400):
        group = names[i:i + 400]
        printed: dict[str, list[tuple]] = {}
        for occ, t, h, l, c in store.db.execute(
                f"SELECT occ, t, h, l, c FROM bars WHERE timeframe = '15Min' AND t >= ? AND t <= ? AND v >= ? AND n >= ? "
                f"AND occ IN ({','.join('?' * len(group))}) ORDER BY occ, t",
                (bars_from, last_t, float(live["min_volume"]), int(live["min_trades"]), *group)):
            printed.setdefault(occ, []).append((fit._ts(t), float(h), float(l), float(c)))
        for occ in group:
            mine = printed.get(occ)
            if not mine:
                continue
            stamps = [b[0] for b in mine]
            parsed = fit.parse_occ(occ)
            times, closes = spots.get(parsed["underlying"], ([], []))
            for t, bid, ask in quotes[occ]:
                at = fit._ts(t)
                k = _bisect.bisect_right(stamps, at) - 1
                if k < 0 or at - stamps[k] > max_gap:
                    continue
                j = _bisect.bisect_right(times, at) - 1
                ranges = [max(0.0, b[1] - b[2]) for b in mine[max(0, k - int(fit.SPREAD_MODEL["range_bars"])):k]]
                pairs.append({"root": parsed["underlying"], "c": mine[k][3], "strike": parsed["strike"], "spot": closes[j] if j >= 0 else None,
                              "bid": bid, "ask": ask, "day": t[:10], "age": at - stamps[k], "expiry": parsed["expiry"],
                              "current": fit.estimate_quote({"c": mine[k][3]}, ranges)[2]})
    return pairs


def judge(fit: Any, pairs: Sequence[Mapping[str, Any]], table: Mapping[str, Any] | None) -> dict[str, Any]:
    """How often a half-spread rule is tighter than the real touch on `pairs` (a buy at c + h under the ask, a sell
    at c - h over the bid), by class and by bucket: `table` (a calibration), or the current estimate when None."""
    etf = set((table or fit.CALIBRATED_SPREADS).get("etf") or ("SPY", "QQQ", "IWM"))

    def half(p: Mapping[str, Any]) -> float:
        if table is None:
            return p["current"]
        measured = fit.calibrated_half(table, p["root"], p["c"], p["strike"], p["spot"])
        return p["current"] if measured is None else max(fit.tick(p["c"]), measured)

    def tally(group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        halves = [half(p) for p in group]
        short = [x for p, h in zip(group, halves) for x in (p["ask"] - (p["c"] + h), (p["c"] - h) - p["bid"]) if x > 1e-9]
        return {"quotes": len(group), "median_half": fit._quantile(halves, 0.5),
                "buy_tighter": round(sum(1 for p, h in zip(group, halves) if p["c"] + h < p["ask"] - 1e-9) / len(group), 4) if group else None,
                "sell_tighter": round(sum(1 for p, h in zip(group, halves) if p["c"] - h > p["bid"] + 1e-9) / len(group), 4) if group else None,
                "median_shortfall": fit._quantile(short, 0.5) or 0.0}

    out: dict[str, Any] = {}
    for kind in ("etf", "stock"):
        group = [p for p in pairs if (p["root"] in etf) == (kind == "etf")]
        if group:
            out[kind] = tally(group)
    buckets = {"etf": sorted(etf), "buckets": [dict(b, index=n) for n, b in enumerate(fit.SPREAD_BUCKETS)]}
    by_bucket: dict[int, list[Mapping[str, Any]]] = {}
    for p in pairs:
        row = fit.spread_bucket(buckets, p["root"], p["c"], p["strike"], p["spot"])
        if row is not None:
            by_bucket.setdefault(row["index"], []).append(p)
    out["buckets"] = [{**{k: v for k, v in fit.SPREAD_BUCKETS[n].items()}, **tally(group)} for n, group in sorted(by_bucket.items())]
    return out


def need_by_group(fit: Any, pairs: Sequence[Mapping[str, Any]], *, day: str, quantile: float) -> list[dict[str, Any]]:
    """The fit's measure (the `quantile` of the larger one-sided need, ask - c and c - bid) by class, days to expiry
    and the print's age (seconds from the bar's close to the quote), with the median quoted half-spread: whether a
    bucket moved because the day had 0-DTE legs, or because a print a snapshot a minute saw is up to a minute older
    than the bar's real close (the need grows with the print's age)."""
    from datetime import date as _date

    etf = set(fit.CALIBRATED_SPREADS.get("etf") or ())
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for p in pairs:
        dte = (_date.fromisoformat(p["expiry"]) - _date.fromisoformat(day)).days
        band = "0" if dte <= 0 else "1-3" if dte <= 3 else "4-7" if dte <= 7 else "8+"
        age = "0-60s" if p["age"] < 60 else "60-180s" if p["age"] < 180 else "180-300s"
        premium = "under 0.5" if p["c"] < 0.5 else "0.5-3" if p["c"] < 3 else "3+"
        kind = "etf" if p["root"] in etf else "stock"
        for key in ((kind, f"dte {band}", premium), (kind, f"age {age}", premium)):
            groups.setdefault(key, []).append(p)
    out = []
    for (kind, split, premium), group in sorted(groups.items()):
        need = max(fit._quantile([p["ask"] - p["c"] for p in group], quantile) or 0.0, fit._quantile([p["c"] - p["bid"] for p in group], quantile) or 0.0)
        out.append({"class": kind, "split": split, "premium": premium, "quotes": len(group), "need": round(max(0.01, need), 4),
                    "quoted_half_median": fit._quantile([(p["ask"] - p["bid"]) / 2 for p in group], 0.5)})
    return out


def calibrate(snapshots: str | Path, *, fit_from: str | Path | None, local_store: str | Path | None, work: str | Path | None,
              quantile: float = 0.975, max_gap: float = 300.0, day: str = "2026-09-25") -> dict[str, Any]:
    """Refit s3/calibration's fill half-spread table with the day's recorded quotes and say how its buckets move:
    the fit on S3's own days again (a control: the same table must come back), on the day alone, and on every day;
    and S3's table, the current estimate and the day's refit judged on the day's pairs (S3's table held out on a new
    day, a Friday with 0-DTE legs)."""
    fit = load_fit(fit_from)
    tmp = tempfile.TemporaryDirectory(prefix="forward-calibration-", dir=work)
    try:
        built = build_calibration_store(snapshots, Path(tmp.name) / "calibration.sqlite", fit, local_store=local_store)
        store = built.pop("store")
        underlier = _underlier(fit, local_store, built.pop("spots"))
        out: dict[str, Any] = {"built": built, "s3_table": fit.CALIBRATED_SPREADS, "quantile": quantile, "max_gap_seconds": max_gap}
        before = f"{day}T00:00:00Z"
        runs = {"s3_days_again": ("", before)} if local_store else {}
        runs.update({"day_only": (before, "9999"), **({"all_days": ("", "9999")} if local_store else {})})
        for name, (start, end) in runs.items():
            table = fit.fit_spread_calibration(store, underlier, quantile=quantile, max_gap=max_gap, start=start, end=end)
            out[name] = table
        # The same fit with quotes within a minute of the bar's close only: the replay fills AT the bar's close, so the
        # drift of up to five more minutes the default pairing admits is not a cost the replay's fill meets.
        out["day_only_gap60"] = fit.fit_spread_calibration(store, underlier, quantile=quantile, max_gap=60.0, start=before, end="9999")
        pairs = calibration_pairs(fit, store, underlier, start=before, end="9999", max_gap=max_gap)
        out["day_pairs"] = {"pairs": len(pairs), "fit_paired": out["day_only"]["fitted_on"]["quotes_paired"],
                            "zero_dte": sum(1 for p in pairs if p["expiry"] == day),
                            "by_root": {root: sum(1 for p in pairs if p["root"] == root) for root in sorted({p["root"] for p in pairs})}}
        out["held_out_on_the_day"] = {"s3_table": judge(fit, pairs, fit.CALIBRATED_SPREADS), "current_estimate": judge(fit, pairs, None),
                                      "day_refit": judge(fit, pairs, out["day_only"]),
                                      **({"all_days_refit": judge(fit, pairs, out["all_days"])} if "all_days" in out else {})}
        out["need_by_group"] = need_by_group(fit, pairs, day=day, quantile=quantile)
        zero = [p for p in pairs if p["expiry"] == day]
        if zero:
            out["held_out_zero_dte"] = {"s3_table": judge(fit, zero, fit.CALIBRATED_SPREADS), "current_estimate": judge(fit, zero, None)}
        # Reviewed Sept 25: the day's pairs are older than S3's (a bar's close synthesized from minute snapshots, and
        # later quotes), and a pair's need grows with its age, so the held-out miss above mixes ages. The same judgement
        # on pairs within a minute of the bar's close (the pairing at max_gap 60 is the pairing at max_gap 300 cut to
        # those pairs), without the day's own expiries, and S3's table judged in sample on S3's own days.
        near = [p for p in pairs if p["age"] <= 60.0]
        etf = set(fit.CALIBRATED_SPREADS.get("etf") or ("SPY", "QQQ", "IWM"))
        s3_pairs = calibration_pairs(fit, store, underlier, start="", end=before, max_gap=max_gap) if local_store else []
        out["held_out_age_matched"] = {
            "median_pair_age_seconds": {name: {"all": _median([p["age"] for p in group]),
                                               **{kind: _median([p["age"] for p in group if (p["root"] in etf) == (kind == "etf")]) for kind in ("etf", "stock")}}
                                        for name, group in (("day", pairs), ("day_within_60s", near), ("s3_days", s3_pairs))},
            "day_within_60s": {"pairs": len(near), "s3_table": judge(fit, near, fit.CALIBRATED_SPREADS),
                               "s3_table_without_the_days_expiries": judge(fit, [p for p in near if p["expiry"] != day], fit.CALIBRATED_SPREADS),
                               "current_estimate": judge(fit, near, None)},
            "s3_days_in_sample": {"pairs": len(s3_pairs), "s3_table": judge(fit, s3_pairs, fit.CALIBRATED_SPREADS),
                                  "s3_table_within_60s": judge(fit, [p for p in s3_pairs if p["age"] <= 60.0], fit.CALIBRATED_SPREADS),
                                  "pairs_within_60s": sum(1 for p in s3_pairs if p["age"] <= 60.0)} if s3_pairs else None}
        store.close()
        return out
    finally:
        tmp.cleanup()


#: When the floor began re-pricing structure limits beyond the book's band (`House._fit_structure_limit`, PR #339):
#: `ops.started` of release 20260925T183013Z-19fb86ee4720 (Deploy V4), read from the House's ledger.
V4_STARTED = "2026-09-25T18:33:52.705Z"


def _write(result: Mapping[str, Any], out: str | None) -> None:
    text = json.dumps(result, indent=1, default=str)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def zero_dte_exposure(founders: Sequence[str] = FOUNDERS) -> dict[str, dict[str, Any]]:
    """Which founders the live chain's missing greeks on today's expiries bear on (reviewed Sept 25, 2026: the first
    reading named six founders as blocked, but five of them can never pick a same-day expiry, and the six it called
    unaffected read the chain's delta first).

    A founder can pick a same-day expiry when the lowest value its nearest leg's expiry parameter may take is 0:
    `near_dte_min` where it declares one (the diagonal's near leg), else `dte_min`, over its PARAMS today and the
    bounds the edit replay and the lab may move it within (`NEEDS.parameter_rules.bounds`). How it reads a
    contract's delta, from its code: 'chain delta only' keeps only the rows the chain gives a delta (the
    `_num(r.get("delta"), None) is not None` filter), so with none on today's expiries it never picks one live;
    'chain delta first' takes the chain's delta where there is one and solves its own only where not (`_delta`), so
    greeks on today's expiries CAN change its strike choice (whether they did on a day, `main` measures: the what-if
    against the session, each founder alone and together). Verdict: `blocked` (can pick today's expiry, chain delta
    only), `may_change_with_greeks` (can pick it, chain delta first), `unaffected` (can never pick it)."""
    out: dict[str, dict[str, Any]] = {}
    for name in founders:
        agent = load_founder(name)
        bounds = dict((agent.needs.get("parameter_rules") or {}).get("bounds") or {})
        key = "near_dte_min" if ("near_dte_min" in agent.params or "near_dte_min" in bounds) else "dte_min"
        values = [v for v in (agent.params.get(key), (bounds.get(key) or [None])[0]) if v is not None]
        can = bool(values) and min(float(v) for v in values) <= 0
        if 'if row["delta"] is not None:\n        return row["delta"]' in agent.code:
            reads = "chain delta first"
        elif '_num(r.get("delta"), None) is not None' in agent.code:
            reads = "chain delta only"
        else:
            reads = "unknown"
        verdict = "unaffected" if not can else {"chain delta only": "blocked", "chain delta first": "may_change_with_greeks"}.get(reads, "unknown")
        out[agent.founder] = {"expiry_parameter": key, "params": agent.params.get(key), "bounds": bounds.get(key),
                              "can_pick_todays_expiry": can, "reads_delta": reads, "verdict": verdict}
    return out


def path_brief(row: Mapping[str, Any], started: str | None) -> dict[str, Any]:
    """One founder on one floor, briefly: what it asked, opened and closed, and its money."""
    opens = [t for t in row["fills"] if t["action"] == "open"]
    return {"started_from": started, "intents_asked": row["intents_asked"], "opens": row["opens"], "closes": row["closes"],
            "closed_structures": row["closed_structures"], "realized_usd": row["realized_usd"],
            "unrealized_usd": round(sum(h["unrealized_usd"] or 0 for h in row["held_at_end"]), 2),
            "held_at_end": [h["market_id"] for h in row["held_at_end"]], "spread_paid_usd": row["spread_paid_usd"],
            "opened": [[t["at"][11:19], t["market_id"], t["held_price"]] for t in opens],
            "asked": [[d["at"][11:19], [(a.get("action"), a.get("structure"), sorted(str(leg.get("occ")) for leg in a.get("legs") or []))
                                        for a in d["asked"]]] for d in row["decisions_with_intents"]]}


def path_ranges(briefs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A founder's figures over several floors (start snapshots, company) as [lowest, highest]."""
    def span(key: str) -> list[float]:
        values = [b[key] for b in briefs]
        return [min(values), max(values)] if values else []
    return {"floors": len(briefs), "realized_usd": span("realized_usd"), "unrealized_usd": span("unrealized_usd"),
            "closed_structures": span("closed_structures"), "opens": span("opens"),
            "floors_that_opened": sum(1 for b in briefs if b["opens"]),
            "structures_opened": sorted({o[1] for b in briefs for o in b["opened"]})}


def compact(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A floor's result for the published file: decision snapshots as counts, the first 12 decisions a founder."""
    if result is None:
        return None
    out = dict(result)
    checks = dict(out["checks"])
    checks["decision_snapshots"] = {agent: len(rows) for agent, rows in (checks.get("decision_snapshots") or {}).items()}
    out["checks"] = checks
    founders = []
    for row in out["founders"]:
        row = dict(row)
        row["decisions_with_intents"] = row["decisions_with_intents"][:12]
        founders.append(row)
    out["founders"] = founders
    return out


def sha256(path: str | Path | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    digest_ = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest_.update(chunk)
    return digest_.hexdigest()


ARCHIVE = Path("~/Work/.options-history").expanduser()


def _default(value: str | None, name: str) -> str | None:
    """An input's path: the flag's ('' for none), else the archived file beside the snapshots when it exists."""
    if value is not None:
        return value or None
    path = ARCHIVE / name
    return str(path) if path.exists() else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", default="forward", choices=("forward", "calibrate", "bar-keys", "query-bars", "query-live", "query-chains"))
    parser.add_argument("--day", default=DAY, help="the session (New York date): the inputs' names, the queries' window, the calibration's day")
    parser.add_argument("--snapshots", default=None, help="the recorder's file (default ~/Work/.options-history/live-<day>.jsonl)")
    parser.add_argument("--house-bars", default=None, help="BARS_QUERY's output (default house-bars-<day>.json beside the snapshots; '' for none)")
    parser.add_argument("--local-store", default=str(ARCHIVE / "options_history.sqlite"))
    parser.add_argument("--live", default=None, help="LIVE_QUERY's output (default house-live-<day>.json): compared, and read by --from-birth")
    parser.add_argument("--from-birth", action="store_true", help="also run each founder from its live first wake, as the floor ran the day")
    parser.add_argument("--v4-at", default=V4_STARTED, help="when the floor began re-pricing structure limits (the --from-birth run)")
    parser.add_argument("--before-v4", action="store_true", help="also run the session as the House ran before V4 (no re-pricing)")
    parser.add_argument("--what-if-0dte-greeks", action="store_true", help="also run the session with greeks on today's expiries (a what-if)")
    parser.add_argument("--paths", type=int, default=1, help="start each floor on each of the first N snapshots it may start on")
    parser.add_argument("--alone", action="store_true", help="also run every founder alone on its own floor (session and what-if)")
    parser.add_argument("--house-chains", default=None, help="CHAINS_QUERY's output (default house-chains-<day>.json): compared")
    parser.add_argument("--founders", default=",".join(FOUNDERS))
    parser.add_argument("--start", default=None, help="ISO time: simulate from here")
    parser.add_argument("--until", default=None, help="ISO time: simulate to here (default the day's 16:00 New York)")
    parser.add_argument("--work", default=None, help="where the floors' ledgers and book files live (deleted after)")
    parser.add_argument("--fit-from", default=None, help="calibrate: s3/calibration's league/options_history.py, while main has no fit")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    founders = [f for f in args.founders.split(",") if f]
    day = args.day
    snapshots = args.snapshots or str(ARCHIVE / f"live-{day}.jsonl")
    if args.command == "bar-keys":
        print(bar_keys(founders))
        return 0
    if args.command.startswith("query-"):  # the read-only query's text for the day, to run on the box through rx.py
        print({"query-bars": lambda: bars_query(day, founders), "query-live": lambda: live_query(day, founders),
               "query-chains": lambda: chains_query(day)}[args.command]())
        return 0
    if args.command == "calibrate":
        began = time.time()
        result = calibrate(snapshots, fit_from=args.fit_from, local_store=args.local_store, work=args.work, day=day)
        result["run"] = {"snapshots_file": snapshots, "snapshots_sha256": sha256(snapshots), "day": day, "seconds": round(time.time() - began, 1)}
        _write(result, args.out)
        return 0
    house_bars = _default(args.house_bars, f"house-bars-{day}.json")
    live_path = _default(args.live, f"house-live-{day}.json")
    chains_path = _default(args.house_chains, f"house-chains-{day}.json")
    until = parse_ts(args.until) if args.until else datetime.combine(datetime.fromisoformat(day).date(), datetime.min.time().replace(hour=16),
                                                                      NEW_YORK).timestamp()
    start = parse_ts(args.start) if args.start else None
    spots = founder_symbols([load_founder(name) for name in founders])  # every floor starts once every founder's symbol is quoted
    live = live_summary(json.loads(Path(live_path).read_text(encoding="utf-8"))) if live_path else None
    offsets = range(max(1, args.paths))
    main_house = None  # the House on main: re-pricing a structure limit beyond the band from the start
    configs: list[tuple[tuple[str, str, int], RunConfig]] = []

    def add(key: tuple[str, str, int], **kw: Any) -> None:
        configs.append((key, RunConfig(label=" / ".join(map(str, key)), start=start, start_after=key[2], require_spots=spots, **kw)))

    variants = [("session", {"reprice_from": main_house})]
    if args.before_v4:
        variants.append(("session_before_v4", {"reprice_from": float("inf")}))
    if args.what_if_0dte_greeks:
        variants.append(("what_if_0dte_greeks", {"reprice_from": main_house, "zero_dte_greeks": True}))
    for name, kw in variants:
        for k in offsets:
            add((name, "together", k), founders=founders, **kw)
            if args.alone and name != "session_before_v4":
                for founder in founders:
                    add((name, f"alone:{founder}", k), founders=[founder], **kw)
    if args.from_birth and live:
        births = {founder: parse_ts(row["first_wake_today"]) for founder, row in live.items() if row.get("first_wake_today")}
        add(("from_birth", "together", 0), founders=founders, starts=births, reprice_from=parse_ts(args.v4_at))
    began = time.time()
    results = run_many(snapshots, [config for _, config in configs], house_bars=house_bars, local_store=args.local_store, work=args.work,
                       until=until, log=lambda text: print(text, file=sys.stderr, flush=True))
    by = {key: result for (key, _), result in zip(configs, results)}
    labels = {"session": "every founder on one floor over the recorded session, the House on main (re-pricing from the start)",
              "session_before_v4": "the same under the House before V4 (no re-pricing: release 20260925T163626Z)",
              "what_if_0dte_greeks": "WHAT-IF, not the House: the recorded session with Black-Scholes greeks on today's expiries, which the live "
                                     "feed does not carry and nothing has validated",
              "from_birth": "each founder from its live first wake on one floor, the House re-pricing from V4 as the floor did"}
    result: dict[str, Any] = {}
    for name in ("session", "session_before_v4", "from_birth", "what_if_0dte_greeks"):
        if (name, "together", 0) in by:
            result[name] = compact(by[(name, "together", 0)])
            result[name]["run"]["label"] = labels[name]
    paths: dict[str, Any] = {"note": "each founder on the floor it shares with every founder ('together') and on a floor of its own ('alone'), "
                                     "started on each of the first snapshots a floor may start on: one figure a floor, [lowest, highest] over them",
                             "starts": sorted({r["checks"]["started_from"] for r in results if r["checks"]["started_from"] and r["run"]["starts"] == {}})}
    for name, _ in variants:
        section: dict[str, Any] = {}
        for founder in founders:
            seed_founder = load_founder(founder).founder
            entry: dict[str, Any] = {}
            for company in ("together", f"alone:{founder}"):
                briefs = []
                for k in offsets:
                    got = by.get((name, company, k))
                    if got is None:
                        continue
                    row = next(f for f in got["founders"] if f["seed"] == founder)
                    briefs.append(path_brief(row, got["checks"]["started_from"]))
                if briefs:
                    tag = "together" if company == "together" else "alone"
                    entry[tag] = {"range": path_ranges(briefs), "per_start": briefs}
            section[seed_founder] = entry
        desks = [by[(name, "together", k)]["desk"] for k in offsets if (name, "together", k) in by]
        section["desk_together"] = {"realized_usd": [min(d["realized_usd"] for d in desks), max(d["realized_usd"] for d in desks)],
                                    "closed_structures": [min(d["closed_structures"] for d in desks), max(d["closed_structures"] for d in desks)],
                                    "unrealized_usd_at_end": [min(d["unrealized_usd_at_end"] for d in desks), max(d["unrealized_usd_at_end"] for d in desks)],
                                    "metric_4_spread_share_of_premium_median": [d["metric_4_spread_share_of_premium_median"] for d in desks],
                                    "agents_positive_on_2_closed": max(d["agents_positive_on_2_closed"] for d in desks)}
        paths[name] = section
    result["paths"] = paths
    exposure = zero_dte_exposure(founders)
    if args.what_if_0dte_greeks:
        for founder in founders:
            for company in ("together", f"alone:{founder}"):
                changed = compared = 0
                for k in offsets:
                    a, b = by.get(("session", company, k)), by.get(("what_if_0dte_greeks", company, k))
                    if a and b:
                        rows = [next(f for f in r["founders"] if f["seed"] == founder) for r in (a, b)]
                        compared += 1
                        changed += path_brief(rows[0], None)["asked"] != path_brief(rows[1], None)["asked"]
                if compared:
                    tag = "together" if company == "together" else "alone"
                    exposure[load_founder(founder).founder][f"what_if_changed_its_orders_{tag}"] = f"{changed} of {compared} starts"
    result["zero_dte_exposure"] = exposure
    result["checks_every_floor"] = {key: sum(r["checks"][key] for r in results) for key in
                                    ("decisions", "decision_snapshot_after_clock", "fills", "fills_not_on_newer_snapshot", "fills_failing_audit")}
    result["checks_every_floor"]["floors"] = len(results)
    result["market"] = results[0]["market"] if results else None
    if live is not None:
        result["live"] = {founder: {k: v for k, v in row.items() if k != "thought_digests"} for founder, row in live.items()}
        result["comparison"] = compare(by.get(("session", "together", 0)), by.get(("from_birth", "together", 0)), live)
        if ("from_birth", "together", 0) in by:
            result["thought_agreement"] = thought_agreement(by[("from_birth", "together", 0)], live)
    if chains_path:
        result["chains_against_the_house"] = compare_chains(snapshots, json.loads(Path(chains_path).read_text(encoding="utf-8")))
    result["inputs"] = {"day": day, "until": iso(until), "seconds": round(time.time() - began, 1),
                        **{name: {"path": path, "sha256": sha256(path)} for name, path in
                           (("snapshots", snapshots), ("house_bars", house_bars), ("house_live", live_path), ("house_chains", chains_path))},
                        "local_store": args.local_store, "v4_at": args.v4_at}
    _write(result, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

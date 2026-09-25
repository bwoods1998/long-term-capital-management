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
only on a leg quote newer than that, every fill is on a strictly newer snapshot (`--check` counts both, and
`league/tests/test_forward_structures.py` pins them).

**What is not the House's** (said in the output): the chain rows carry Black-Scholes IV and delta from each contract's
mid (r 4%, `options_history.implied_vol`), where the live chain carries Alpaca's greeks (the recorder did not keep
them); the recorded bands (4% of spot on the ETFs, 12% on the stocks) are narrower than the chain's 20%; the
underlying bars are the House's own recordings of the day (`recordings.sqlite`, read-only, `--house-bars`), completed
from the local history (`underlier_bars`) and, failing both, from the snapshots' mids; the tick is one a snapshot (60 s;
the live House's ticks ran 60-200 s); all twelve wake on one clock from the first snapshot with sizes.

Usage (ONE process at a time on the shared machine; it streams the file, about 150 MB of memory):
    python3 scripts/forward_structures.py --snapshots ~/Work/.options-history/live-2026-09-25.jsonl \
        --house-bars house_bars.json --out docs/runs/data/forward-structures-2026-09-25.json
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
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
from league.ledger import Ledger, now_iso  # noqa: E402
from league.options_history import implied_vol, bs_delta, years_to  # noqa: E402
from league.options_shadow import OptionsShadowBroker, stamp  # noqa: E402
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
DEFAULT_HOUSE_BARS = None


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
    strike first. `iv` and `delta` are Black-Scholes from the mid against the underlying's mid (r 4%): the recorder
    did not keep Alpaca's greeks."""

    option_feed = "opra"

    def __init__(self, source: LegSource):
        self.source = source
        self._greeks: dict[tuple[int, str], tuple[float | None, float | None]] = {}

    def option_chain(self, underlying: str, *, expiry_from: str, expiry_to: str, limit: int = 1000) -> list[dict[str, Any]]:
        snap = self.source.current
        if snap is None:
            return []
        clock = self.source.clock()
        if snap.t > clock + 1e-9:
            raise AssertionError("look-ahead in the chain")
        under = underlying.upper()
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
                self._greeks[key] = greeks(row, mid_spot, snap.t)
                if len(self._greeks) > 200_000:
                    self._greeks.clear()
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

    def load_house(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
    """`options_features` for a strategy that asks for them (`House.snapshot`: `options_history.features_at`), read
    from the local copy of the store; nothing is ever written to it."""

    def __init__(self, store: str | Path | None):
        self.path = None if store is None else Path(store).expanduser()

    def features_at(self, symbols: Sequence[str], now_ts: float) -> dict[str, Any]:
        if self.path is None or not self.path.exists():
            return {}
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            out = {}
            for symbol in symbols:
                row = db.execute("SELECT payload FROM features WHERE symbol = ? AND version = 'bs-close-v2' AND available_at <= ? "
                                 "ORDER BY available_at DESC LIMIT 1", (str(symbol).upper(), iso(now_ts))).fetchone()
                if row:
                    out[str(symbol).upper()] = json.loads(row[0])
            return out
        finally:
            db.close()


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

    def alert(self, level: str, text: str) -> None:
        self.alerts.append((iso(self.clock()), level, text[:400]))

    def _keep_option_quotes(self, broker: Any, chain: Any, spot: Any) -> None:
        return None  # the live House keeps them in its options history; the forward test writes nothing


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


@dataclass
class Tally:
    wakes: int = 0
    errors: int = 0
    last_error: str = ""
    intents: int = 0
    dropped: list[str] = field(default_factory=list)
    thoughts: list[tuple[str, str]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)


# ------------------------------------------------------------------------------------------ the run
def run(snapshots: str | Path, *, house_bars: str | Path | None, local_store: str | Path | None, founders: Sequence[str] = FOUNDERS,
        work: str | Path | None = None, start: float | None = None, until: float | None = None, starts: Mapping[str, float] | None = None,
        mark_every: float = MARK_EVERY, keep_thoughts: int = 6, log: Callable[[str], None] | None = None,
        decide_override: Mapping[str, Callable[[dict], dict]] | None = None) -> dict[str, Any]:
    """The forward test. `start`/`until` bound the simulated session (epoch seconds); `starts` holds a founder back
    until its own first wake (the live birth, for the comparison); `decide_override` replaces a founder's decide (the
    tests). Returns the result document (`summarize`)."""
    say = log or (lambda text: None)
    clock = SimClock()
    source = LegSource(clock)
    chain_broker = ChainBroker(source)
    data = Bars(clock, source)
    agents = [load_founder(name) for name in founders]
    if decide_override:
        for agent in agents:
            if agent.seed in decide_override:
                agent.decide = decide_override[agent.seed]
    symbols = sorted({str(s).upper() for a in agents for s in a.needs.get("symbols") or ()})
    timeframes = sorted({str((a.needs.get("bars") or {}).get("timeframe") or "5Min") for a in agents})
    if house_bars:
        data.load_house(house_bars)
    tmp = tempfile.TemporaryDirectory(prefix="forward-structures-", dir=work)
    root = Path(tmp.name)
    ledger = Ledger(root / "ledger.sqlite", clock=clock)
    broker = OptionsShadowBroker(root / "options-shadow.json", source, underlying_close=None, starting_cash="100000", clock=clock)
    book = Book(BOOK, broker, ledger, fees=Fees("alpaca", option_clearing=True), real_money=False, clock=clock, market_open=market_hours)
    books = {"alpaca-paper": _ChainBook(chain_broker), BOOK: book}
    shim = HouseShim(clock, ledger, books, data, Features(local_store))
    tallies = {a.id: Tally() for a in agents}
    next_wake: dict[str, float] = {}
    last_mark = -1e18
    checks = {"decisions": 0, "decision_snapshot_after_clock": 0, "fills": 0, "fills_not_on_newer_snapshot": 0, "snapshots": 0,
              "first_snapshot": None, "last_snapshot": None, "sized_from": None}
    decided_on: dict[str, list[tuple[float, int]]] = {}  # agent -> [(decision clock, snapshot index)]
    fill_snapshot: dict[str, int] = {}
    fill_log: list[dict[str, Any]] = []
    seen_fills = 0
    started_book = False
    snap = None
    try:
        for snap in read_snapshots(snapshots, until=until):
            if start is not None and snap.t < start:
                data.observe(snap)
                continue
            clock.now = snap.t
            source.current = snap
            data.observe(snap)
            checks["snapshots"] += 1
            checks["first_snapshot"] = checks["first_snapshot"] or iso(snap.t)
            checks["last_snapshot"] = iso(snap.t)
            if not any(r.get("bid_size") is not None for r in snap.rows.values()):
                continue  # no leg sizes (the recorder's first line): the broker could fill nothing on it; nothing starts on it
            if not started_book:
                started_book = True
                checks["sized_from"] = iso(snap.t)
                if local_store:
                    data.load_local(local_store, symbols, timeframes, snap.t)
                for agent in agents:
                    book.stake(agent.id, STAKE, note="rung 1 stake")
                    book.limits[agent.id] = Limits(LIMITS[0], LIMITS[1], asset_classes=("option",))
                    next_wake[agent.id] = max(snap.t, float((starts or {}).get(agent.founder) or snap.t))
            # The House's tick: the broker's fills, the book's poll, the wakes and their batch, the expiry rules, the marks.
            broker.advance()
            book.poll()
            fills = [row for row in ledger.iter(kinds=("book.fill",))]
            for row in fills[seen_fills:]:
                checks["fills"] += 1
                order_snap = fill_snapshot.get(str(row.payload.get("order_id") or ""))
                fill_log.append({"agent": row.agent, "order_id": row.payload.get("order_id"), "side": row.payload.get("side"),
                                 "submitted_snapshot": order_snap, "filled_snapshot": snap.index, "at": row.at, "price": row.payload.get("price")})
                if order_snap is None or order_snap >= snap.index:
                    checks["fills_not_on_newer_snapshot"] += 1
            seen_fills = len(fills)
            batch = []
            for agent in agents:
                if next_wake.get(agent.id, float("inf")) > clock():
                    continue
                next_wake[agent.id] = clock() + agent.wake_minutes * 60
                tally = tallies[agent.id]
                tally.wakes += 1
                ctx = shim.snapshot(agent, book)
                ctx = json.loads(json.dumps(ctx, default=str))  # the box sees JSON, as the sandbox passes it
                checks["decisions"] += 1
                if source.current is None or source.current.t > clock() + 1e-9:
                    checks["decision_snapshot_after_clock"] += 1
                decided_on.setdefault(agent.id, []).append((clock(), snap.index))
                try:
                    answer = agent.decide(ctx)
                    if not isinstance(answer, dict):
                        raise TypeError(f"decide returned {type(answer).__name__}")
                    answer = json.loads(json.dumps(answer, default=str))
                except Exception as exc:  # noqa: BLE001 - a strategy's error is its wake's, as in its box
                    tally.errors += 1
                    tally.last_error = f"{type(exc).__name__}: {str(exc)[:300]} | {traceback.format_exc(limit=2)[-300:]}"
                    continue
                shim._state["memory"][agent.id] = answer.get("memory") or {}
                thought = str(answer.get("thought") or "").strip()
                if thought:
                    tally.thoughts.append((iso(clock()), thought[:600]))
                    del tally.thoughts[:-keep_thoughts]
                for order_id in answer.get("cancels") or ():
                    if isinstance(order_id, str):
                        book.cancel(agent.id, order_id)
                rows = [r for r in (answer.get("intents") or []) if isinstance(r, Mapping)]
                intents, dropped = shim._intents(agent, book, rows)
                tally.intents += len(rows)
                tally.dropped += dropped
                if rows:
                    tally.decisions.append({"at": iso(clock()), "snapshot": snap.index, "asked": [
                        {k: r.get(k) for k in ("structure", "action", "quantity", "limit_price", "legs", "reason")} for r in rows]})
                batch += intents
            if batch:
                for outcome in book.submit(batch):
                    if outcome.order_id:
                        fill_snapshot[str(outcome.order_id)] = snap.index
            shim._horizon_exits(book, float("inf"))
            for working in book.open_orders():
                fill_snapshot.setdefault(str(working.order_id), snap.index)
            if clock() - last_mark >= mark_every:
                book.mark()
                last_mark = clock()
            if snap.index % 30 == 0:
                say(f"{iso(snap.t)} snapshot {snap.index}: fills {checks['fills']}, open orders {len(book.open_orders())}")
        if snap is not None and started_book:
            book.mark()
        result = summarize(agents, book, broker, ledger, shim, tallies, checks, source, data, snap)
        result["checks"]["fill_log"] = fill_log
        result["checks"]["decision_snapshots"] = {agent: [[iso(at), index] for at, index in rows] for agent, rows in decided_on.items()}
        return result
    finally:
        ledger.close()
        tmp.cleanup()


def _money(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def summarize(agents, book: Book, broker: OptionsShadowBroker, ledger: Ledger, shim: HouseShim, tallies: Mapping[str, Tally],
              checks: Mapping[str, Any], source: LegSource, data: Bars, last: Snapshot | None) -> dict[str, Any]:
    """Per founder: its wakes, intents, House refusals and drops, book refusals, opens and closes (every fill, at
    held and natural prices), realized P&L after fees, what it still holds at the last snapshot with its mark (the
    structure's bid) and unrealized P&L, and its latest thoughts."""
    fills = [row for row in ledger.iter(kinds=("book.fill",))]
    refused = [row for row in ledger.iter(kinds=("book.refused",))]
    out = []
    for agent in agents:
        account = book.account(agent.id)
        mine = [row for row in fills if row.agent == agent.id]
        trades = []
        for row in mine:
            p = row.payload
            inst = p.get("instrument") or {}
            spec = core.spec_of_code(str(inst.get("market_id")), venue=BOOK) if inst.get("market_id") else None
            price = Decimal(str(p["price"]))
            natural = None if spec is None else float(core.natural_price(spec, price))
            trades.append({"at": row.at, "side": p.get("side"), "action": "open" if p.get("side") == "buy" else "close",
                           "structure": spec.type if spec else None, "market_id": inst.get("market_id"), "quantity": float(Decimal(str(p["quantity"]))),
                           "held_price": float(price), "natural_price": natural, "fee_usd": _money(p.get("fee_usd") or 0),
                           "realized_usd": _money(p["realized"]) if p.get("realized") is not None and p.get("side") == "sell" else None,
                           "flat": bool(p.get("flat")), "reason": str(p.get("reason") or "")[:240]})
        held = []
        for holding in account.holdings.values():
            inst = holding.instrument
            mark = book.marks.get(inst.key)
            spec = structures.spec_of(inst)
            row = {"market_id": inst.market_id, "structure": spec.type, "quantity": float(holding.quantity),
                   "held_cost": float(holding.average_cost), "mark": None if mark is None else float(mark),
                   "unrealized_usd": None if mark is None else _money((mark - holding.average_cost) * inst.multiplier * holding.quantity),
                   "expiry": spec.expiry}
            if last is not None and spec.type not in structures.TWO_EXPIRIES:
                touch = last.spot.get(spec.underlying)
                if touch:
                    value = structures.intrinsic(spec, Decimal(str(round((touch[0] + touch[1]) / 2, 4))))
                    row["intrinsic_at_last_spot"] = float(value)
            held.append(row)
        tally = tallies[agent.id]
        reasons: dict[str, int] = {}
        for row in refused:
            if row.agent == agent.id:
                for reason in row.payload.get("reasons") or ["?"]:
                    reasons[str(reason)[:160]] = reasons.get(str(reason)[:160], 0) + 1
        closes = [t for t in trades if t["action"] == "close" and t["flat"]]
        out.append({
            "founder": agent.founder, "seed": agent.seed, "wake_minutes": agent.wake_minutes, "wakes": tally.wakes, "decide_errors": tally.errors,
            "last_error": tally.last_error, "intents_asked": tally.intents, "dropped": tally.dropped[:10], "refusals": reasons,
            "opens": sum(1 for t in trades if t["action"] == "open"), "closes": sum(1 for t in trades if t["action"] == "close"),
            "closed_structures": len(closes), "realized_usd": _money(account.realized), "fees_usd": _money(account.fees),
            "closed_realized_usd": [t["realized_usd"] for t in closes],
            "equity_usd": _money(book.equity(agent.id)), "stake_usd": float(STAKE), "held_at_end": held, "fills": trades,
            "decisions_with_intents": tally.decisions[:40], "last_thoughts": tally.thoughts,
        })
    orders = [order for order in broker._orders.values()]
    statuses: dict[str, int] = {}
    for order in orders:
        statuses[order.status] = statuses.get(order.status, 0) + 1
    served = source.served
    return {"founders": out,
            "desk": {"closed_structures": sum(f["closed_structures"] for f in out), "realized_usd": _money(sum(Decimal(str(f["realized_usd"])) for f in out)),
                     "agents_positive_on_2_closed": sum(1 for f in out if f["closed_structures"] >= 2 and f["realized_usd"] > 0),
                     "held_at_end": sum(len(f["held_at_end"]) for f in out),
                     "unrealized_usd_at_end": _money(sum(Decimal(str(h["unrealized_usd"] or 0)) for f in out for h in f["held_at_end"]))},
            "broker": {"orders": len(orders), "statuses": statuses, "fills": len(broker._fills)},
            "checks": {**checks, "leg_reads": len(served)},
            "alerts": shim.alerts[-40:], "bar_sources": data.sources(),
            "bars_from_snapshot_mids": dict(sorted(data.from_mids.items()))}


# ------------------------------------------------------------------------------------------ the live House's day
#: The read-only queries the forward test's inputs came from, run on the House box through the session's
#: `rx.py` (sqlite `mode=ro`; no order, no write): the House's recorded bars of the day (argv[1]: the bar keys,
#: `;`-separated, as `bar_keys()` prints them) and the live structure founders' day (krasker-22..33).
BARS_QUERY = r'''# READ-ONLY (sqlite mode=ro): the underlying bars and features the House showed today's structure founders, as it
# recorded them (recordings.sqlite, `House._cached`), the earliest and the latest recording of each key since 13:00Z;
# and the options feature rows available since Sept 24 12:00Z for the skew founder's symbols. No order, no write.
import gzip, json, sqlite3, sys, time
keys = sys.argv[1].split(";")
since = 1790341200.0  # 2026-09-25T13:00:00Z
db = sqlite3.connect('file:/workspace/state/recordings.sqlite?mode=ro', uri=True)
out = {"bars": {}, "features": []}
for key in keys:
    got = {}
    for label, order in (("earliest", "ASC"), ("latest", "DESC")):
        row = db.execute(f"SELECT received, payload FROM snapshots WHERE source = ? AND received >= ? ORDER BY received {order} LIMIT 1", (key, since)).fetchone()
        if row:
            got[label] = {"received": row[0], "value": json.loads(gzip.decompress(row[1]))}
    out["bars"][key] = got
oh = sqlite3.connect('file:/workspace/state/options_history.sqlite?mode=ro', uri=True)
for r in oh.execute("SELECT symbol, day, version, available_at, payload FROM features WHERE available_at >= '2026-09-24T12:00:00Z' AND symbol IN ('F','AAL','CCL','RIVN','SPY','QQQ','IWM','BAC','T','PFE','SOFI','SNAP','INTC','HOOD')"):
    out["features"].append({"symbol": r[0], "day": r[1], "version": r[2], "available_at": r[3], "payload": json.loads(r[4])})
print(json.dumps(out, separators=(",", ":")))
'''
LIVE_QUERY = r'''# READ-ONLY (sqlite mode=ro): what the live structure founders krasker-22..33 did today on options-shadow: birth
# (founder, family, code sha), strategy changes, wakes, intents, House/book refusals, fills, the latest marks and
# thoughts. No order, no write.
import json, sqlite3
db = sqlite3.connect('file:/workspace/state/ledger.sqlite?mode=ro', uri=True)
agents = [f"krasker-{i}" for i in range(22, 34)]
marks = ",".join("?" * len(agents))
out = {a: {"born": None, "strategy": [], "woke": [], "intents": [], "refused": [], "fills": [], "orders": [], "mark": None, "thoughts": []} for a in agents}
for at, kind, agent, payload in db.execute(
        f"SELECT at, kind, agent, payload FROM ledger WHERE at >= '2026-09-25T13:00:00Z' AND agent IN ({marks}) AND kind IN "
        "('agent.born','agent.strategy','agent.woke','agent.intent','book.refused','book.fill','book.order','book.mark','agent.thought') ORDER BY seq", agents):
    p = json.loads(payload)
    row = out[agent]
    if kind == "agent.born":
        row["born"] = {"at": at, "founder": p.get("founder"), "family": p.get("family"), "code_sha256": p.get("code_sha256"), "style": p.get("style")}
    elif kind == "agent.strategy":
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
        row["thoughts"] = (row["thoughts"] + [[at, str(p.get("text") or "")[:500]]])[-4:]
for at, agent, payload in db.execute(f"SELECT at, agent, payload FROM ledger WHERE kind = 'agent.born' AND agent IN ({marks})", agents):
    p = json.loads(payload)
    if out[agent]["born"] is None:
        out[agent]["born"] = {"at": at, "founder": p.get("founder"), "family": p.get("family"), "code_sha256": p.get("code_sha256"), "style": p.get("style")}
print(json.dumps(out, separators=(",", ":")))
'''


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
    structures it still held at the last row, strategy changes (a rewrite, a pause), and its latest thought."""
    out = {}
    for agent, row in sorted(live.items()):
        founder = (row.get("born") or {}).get("founder") or (row.get("born") or {}).get("family")
        if not founder:
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
        out[founder] = {"agent": agent, "born": (row.get("born") or {}).get("at"), "first_wake_today": woke[0][0] if woke else None,
                        "wakes": len(woke), "intents": sum(1 for i in row.get("intents") or [] if i["at"] >= since and i.get("book") == BOOK),
                        "refusals": reasons, "opens": sum(1 for f in fills if f["side"] == "buy"), "closes": len(closes),
                        "closed_structures": sum(1 for f in closes if f.get("flat")),
                        "realized_usd": round(sum(float(f["realized"]) for f in closes if f.get("realized") is not None), 2),
                        "fees_usd": round(sum(float(f.get("fee_usd") or 0) for f in fills), 2),
                        "fills": [{k: f.get(k) for k in ("at", "side", "market_id", "quantity", "price", "fee_usd", "realized", "flat", "reason")} for f in fills],
                        "held_at_end": [code for code, q in held.items() if q > 0],
                        "strategy_changes": [{k: c.get(k) for k in ("at", "control", "code_sha256", "note")} for c in row.get("strategy") or []],
                        "last_mark": row.get("mark"), "last_thought": (row.get("thoughts") or [[None, None]])[-1]}
    return out


def compare(session: Mapping[str, Any], from_birth: Mapping[str, Any] | None, live: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row a founder: the forward test over the whole recorded session, the forward test from the live founder's
    first wake, and the live founder."""
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
        out.append({"founder": founder, "forward_session": brief(a.get(founder)), "forward_from_birth": brief(b.get(founder)),
                    "live": None if mine is None else {k: mine[k] for k in ("agent", "first_wake_today", "wakes", "intents", "opens", "closes",
                                                                             "closed_structures", "realized_usd", "held_at_end", "refusals",
                                                                             "strategy_changes")}})
    return out


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


def _underlier(fit: Any, local_store: str | Path | None, spots: Mapping[str, Sequence[tuple[float, float]]]) -> Callable[..., list[dict[str, Any]]]:
    """`underlier_bars(symbol, "15Min", start, end)` for the fit's moneyness: the local copy's bars through Sept 24,
    then the day's 15-minute closes of the snapshots' mids (close-stamped)."""
    stored = fit.stored_underlier(fit.OptionsHistory(Path(local_store).expanduser())) if local_store else None
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
        return out
    finally:
        tmp.cleanup()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", default="forward", choices=("forward", "calibrate", "bar-keys"))
    parser.add_argument("--fit-from", default=None, help="calibrate: s3/calibration's league/options_history.py, when main has no fit")
    parser.add_argument("--live", default=None, help="the live founders' day (JSON of LIVE_QUERY's output): compared, and --from-birth reads it")
    parser.add_argument("--from-birth", action="store_true", help="also run each founder from its live first wake (the comparison run)")
    parser.add_argument("--snapshots", default=str(Path("~/Work/.options-history/live-2026-09-25.jsonl").expanduser()))
    parser.add_argument("--house-bars", default=None, help="the House's recorded bars of the day (JSON from a read-only query)")
    parser.add_argument("--local-store", default=str(Path("~/Work/.options-history/options_history.sqlite").expanduser()))
    parser.add_argument("--founders", default=",".join(FOUNDERS))
    parser.add_argument("--start", default=None, help="ISO time: simulate from here")
    parser.add_argument("--until", default=None, help="ISO time: simulate to here")
    parser.add_argument("--starts", default=None, help="JSON {founder family: ISO first wake} (the live births)")
    parser.add_argument("--work", default=None, help="where the run's ledger and book file live (deleted after)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--label", default="forward")
    args = parser.parse_args(argv)
    starts = None
    if args.starts:
        starts = {k: parse_ts(v) for k, v in json.loads(Path(args.starts).read_text() if Path(args.starts).exists() else args.starts).items()}
    began = time.time()
    if args.command == "bar-keys":
        print(bar_keys([f for f in args.founders.split(",") if f]))
        return 0
    if args.command == "calibrate":
        result = calibrate(args.snapshots, fit_from=args.fit_from, local_store=args.local_store, work=args.work)
        result["run"] = {"snapshots_file": str(args.snapshots), "seconds": round(time.time() - began, 1)}
        text = json.dumps(result, indent=1, default=str)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0
    founders = [f for f in args.founders.split(",") if f]
    common = dict(house_bars=args.house_bars, local_store=args.local_store, founders=founders, work=args.work,
                  start=parse_ts(args.start) if args.start else None, until=parse_ts(args.until) if args.until else None,
                  log=lambda text: print(text, file=sys.stderr, flush=True))
    session = run(args.snapshots, starts=starts, **common)
    session["run"] = {"label": args.label, "seconds": round(time.time() - began, 1), "starts": {k: iso(v) for k, v in (starts or {}).items() if v}}
    if not args.live:
        result = session
    else:
        live = live_summary(json.loads(Path(args.live).read_text(encoding="utf-8")))
        result = {"session": session, "live": live}
        if args.from_birth:
            births = {founder: parse_ts(row["first_wake_today"]) for founder, row in live.items() if row.get("first_wake_today")}
            began = time.time()
            result["from_birth"] = run(args.snapshots, starts=births, **common)
            result["from_birth"]["run"] = {"label": "from each live founder's first wake", "seconds": round(time.time() - began, 1),
                                           "starts": {k: iso(v) for k, v in births.items() if v}}
        result["comparison"] = compare(session, result.get("from_birth"), live)
    result["inputs"] = {"snapshots_file": str(args.snapshots), "house_bars": args.house_bars, "local_store": args.local_store, "live": args.live}
    text = json.dumps(result, indent=1, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

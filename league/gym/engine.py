"""The Gym's replay: day-major batching, the engine's clock, honest fills, the venue's rules.

    results = run(programs, store, RunConfig(window="train", roots=("SPY",)))

For each trading day of the window the engine loads each root's chain ONCE (`store.Store.chain`),
then steps every program of the batch through the day minute by minute: a snapshot of a root at a
minute is built once and shared by every program that looks at it that minute, and dropped after.
A program is called at its NEEDS cadence and sees only minute m's row (and the underlying up to m,
and the prior sessions); its orders meet the NBBO of minute m + 1 and later (`fills.py`). Nothing a
program sees at minute m is computed from anything after m: the engine owns the clock.

The day of a program, minute index i from 1 (09:31) to the last minute before the close:
1. its working orders meet row i (arrivals first sent at i - 1);
2. the venue acts at row i: opening orders on an expiring contract are cancelled at the open
   cutoff (15:00), closing ones at the close cutoff (15:10; 15:25 SPY/QQQ); an equity position with
   a leg expiring today that is in the money or within 1% of it (`venue.near_money`), or a long call
   or put with a bid, is closed at the natural price by the House from 10 minutes before the close
   cutoff until the cutoff (the live path's rule, `league/live/step.py` `_expiry_close`), and one in
   or near the money by the venue's liquidation from 15:30; the rest is left to expire;
3. on a decision minute, decide(ctx) runs and its intents become orders arriving at i + 1.
At the close: working orders expire; positions expiring today settle (index: cash at the closing
level, never liquidated; equity legs that were not closed: exercised at $0.01 in the money, and a
net share position is marked to the next session's first price; nothing in the money: expired, with
no fee); every position is marked at the mid; the day's P&L is the change in cash plus marks. At the
window's end every open position is closed at the natural price of the last minute (or marked, where
a leg has no quote). A segment of a split run (`RunConfig.split_mark`) ends differently: what is
still open is valued at the mid with no fee (an accounting split, not a trade), and a later segment's
programs first replay `RunConfig.warmup` prior days without trading (`batch.py`).

A STOCK SPLIT is a different thing: the OCC adjusts a name's listed options (strikes, deliverable,
often the symbol), so a contract held into the split session is not in that session's chain under its
old key and can be neither marked nor closed; left alone it would expire against the post-split price
(a call spread worthless, a put spread at its width). The splits come from a public table
(`events.SPLITS`: root, ex-date, factor; announced weeks ahead, as the macro calendars are), never from
the prices: on the EVE (the root's last replayed session before the ex-date, `split_eves`) every
position on that root still open at the close is closed at the natural of the session's last minute
that quotes every leg, with its fees (exit reason `stock_split`; where no minute of the last half hour
quotes them all, leg by leg at each leg's last quoted natural there, else its intrinsic value at the
eve's level, with fees: `stock_split_legs`), assigned shares of that root are marked at the eve's
settlement level, and an opening order on it that would be held across the split (a leg expiring
after the eve) is not placed. That refusal is counted in the result's reject reasons but never said to
the program (`ctx.rejects`). The price cross-check (`split_alert`: the prior session's last price over
the session's first near a whole factor) only raises an alert, recorded in the result's `stock_splits`
block: read on its own it would take an overnight crash of about half for a 2-for-1 split, a look
ahead. A run with no split in the table for its roots and days, and no alert, runs exactly as before.

Deterministic: the same programs, parameters, store files, fill model and window give the same
result (`results.py` hashes it). numpy only here; the store reader brings pyarrow.
"""

from __future__ import annotations

import bisect
import copy
import datetime as dt
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np

from . import ENGINE_VERSION, fills as F, greeks as G, legs as L, venue
from .ctx import Snapshot, build_ctx, order_row, position_row, underlying_view
from .events import EVENT_NAMES, EventCalendar, rate_on
from .runtime import Program

if TYPE_CHECKING:  # pragma: no cover
    from .day import DayChain
    from .store import Store


def settlement_level(u: Any) -> float:
    """The level an expiring option settles or is exercised against: the store's recorded settlement
    (`settle`) where it has one, else the last one-minute bar's close, else the price in force at the
    close minute. For XSP and SPXW that last fallback is the 16:00 snapshot of the index, an
    approximation of the official SPX close (a few hundredths of a point off on a normal day)."""
    for series in (u.settle, u.close, u.price):
        if series is not None:
            known = series[np.isfinite(series)]
            if known.size:
                return float(known[-1])
    return float("nan")


#: The price cross-check (`split_factor`): the prior session's last price over the next session's first within this share
#: of an integer k (2..SPLIT_MAX_FACTOR), or of 1/k. On the Gym image's 25 roots, 2022-2025 (Sept 28, 2026), the eight
#: splits of `events.SPLITS` in those years sit within 0.06 of theirs and the largest overnight move that was not a split
#: (a 29% gap down) is 0.29 short of 2. It never closes anything: only the table does (the module docstring).
SPLIT_TOLERANCE = 0.15
SPLIT_MAX_FACTOR = 100


def split_factor(before: float, after: float) -> float | None:
    """The split the prices suggest between two sessions of one root, from the prior session's last price (`before`)
    and the next session's first (`after`): k for a k-for-1 split, 1/k for a 1-for-k reverse split, None for none."""
    try:
        before, after = float(before), float(after)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(before) and math.isfinite(after) and before > 0 and after > 0):
        return None
    ratio = before / after
    k = round(ratio if ratio >= 1.0 else 1.0 / ratio)
    if not 2 <= k <= SPLIT_MAX_FACTOR:
        return None
    off = ratio / k - 1.0 if ratio >= 1.0 else ratio * k - 1.0
    if abs(off) > SPLIT_TOLERANCE:
        return None
    return float(k) if ratio >= 1.0 else 1.0 / k


def split_label(factor: float) -> str:
    """'3-for-1' (a split), '1-for-10' (a reverse split)."""
    return f"{factor:g}-for-1" if factor >= 1.0 else f"1-for-{1.0 / factor:g}"


def _splits(table: Any = None) -> tuple[tuple[str, dt.date, float], ...]:
    from . import events as EV

    return tuple(EV.SPLITS if table is None else table)


def split_eves(store: Any, roots: Sequence[str], days: Sequence[dt.date], table: Any = None) -> list[dict[str, Any]]:
    """The table's splits (`events.SPLITS`) that fall on the run: for each split of a root in `roots`, its eve is the
    root's last replayed session before the ex-date (a day of `days` whose chain the engine loads: NBBO and underlying),
    when the run replays the root on or after the ex-date or that session is the calendar's last one before it (a run or
    segment ending on the eve closes at the natural too, as the whole run does). Reads the calendar and the files'
    presence only, never a price. [{"root", "ex_date", "factor", "eve"}], by eve."""
    splits = [s for s in _splits(table) if s[0] in set(roots)]
    if not splits or not days:
        return []
    calendar = sorted(store.trading_days())
    out = []
    for root, ex, factor in splits:
        mine = [d for d in days if store.has("nbbo", root, d) and store.has("underlying", root, d)]
        before = [d for d in mine if d < ex]
        if not before:
            continue
        eve = before[-1]
        i = bisect.bisect_right(calendar, eve)
        if any(d >= ex for d in mine) or (i < len(calendar) and calendar[i] >= ex):
            out.append({"root": root, "ex_date": ex.isoformat(), "factor": float(factor), "eve": eve})
    return sorted(out, key=lambda s: (s["eve"], s["root"]))


def split_alert(root: str, prior_day: dt.date | None, prior_close: float, day: dt.date, first: float,
                table: Any = None) -> dict[str, Any] | None:
    """The price cross-check of one root's overnight from `prior_day` (its last session, closing at `prior_close`) to
    `day` (opening at `first`), against the table: an alert when the prices show a split-like ratio the table has no
    split for in (prior_day, day], or the table has one the prices do not show; None when they agree. An alert is
    recorded in the result, never acted on."""
    if prior_day is None:
        return None
    listed = [float(f) for r, ex, f in _splits(table) if r == root and prior_day < ex <= day]
    want = math.prod(listed) if listed else None
    seen = split_factor(prior_close, first)
    if want is None and seen is None:
        return None
    if want is not None and seen is not None and abs(seen / want - 1.0) < 1e-9:
        return None
    ratio = float(prior_close) / float(first) if (math.isfinite(prior_close) and math.isfinite(first) and first > 0) else None
    return {"root": root, "day": day.isoformat(), "prior_day": prior_day.isoformat(),
            "ratio": None if ratio is None else round(ratio, 4), "table": want, "prices": seen}


def split_check(store: Any, roots: Sequence[str], days: Sequence[dt.date], table: Any = None) -> list[dict[str, Any]]:
    """The cross-check over a store's days (`batch.py --split-check`): every alert (`split_alert`) between consecutive
    days of `days` on which each root has an underlying file."""
    out = []
    for root in roots:
        prior: tuple[dt.date, float] | None = None
        for day in days:
            if not store.has("underlying", root, day):
                continue
            first, last = _price_ends(store, root, day)
            if prior is not None:
                alert = split_alert(root, prior[0], prior[1], day, first, table)
                if alert is not None:
                    out.append(alert)
            if math.isfinite(last):
                prior = (day, last)
    return out


def _price_ends(store: Any, root: str, day: dt.date) -> tuple[float, float]:
    ends = getattr(store, "price_ends", None)
    if callable(ends):
        return ends(root, day)
    price = np.asarray(store.underlying(root, day).price, dtype=np.float64)
    known = price[np.isfinite(price) & (price > 0)]
    return (float(known[0]), float(known[-1])) if known.size else (math.nan, math.nan)


class Unsaid(L.Refused):
    """A refusal counted in the result's reject reasons but never said to the program (`ctx.rejects`)."""


@dataclass
class RunConfig:
    """One run's settings (every one of them is part of the run's hash)."""

    window: str = "train"
    roots: tuple[str, ...] = ()      # the run's universe; a program trades its NEEDS roots within it (all, if empty)
    capital: float = 10_000.0        # each program's account
    stress: float = 1.0              # half-spread multiplier on every fill (1.5 = the gate's stress run)
    timeout: float = 1.0             # seconds a decide call may take
    max_errors: int = 25             # errors before a program is disqualified
    max_orders_day: int = 60         # orders (opens and closes) a program may send a day
    max_decide_seconds: float = 900.0  # a program's decide calls may take this long in all, a run
    start: dt.date | None = None     # cut the window (the inner loop's segments)
    end: dt.date | None = None
    fill_model: F.FillModel = field(default_factory=F.FillModel)
    #: A segment another segment continues (a split run): at its end, open positions are valued at the
    #: mid with no fee (exit reason `split_mark`), never closed at the natural.
    split_mark: bool = False
    #: Trading days of the window before `start` that each program replays first, deciding but never
    #: trading, so its STATE is warm when the segment begins (0: none).
    warmup: int = 0

    def identity(self) -> dict[str, Any]:
        out = {"window": self.window, "roots": sorted(self.roots), "capital": self.capital, "stress": self.stress,
               "max_orders_day": self.max_orders_day, "start": self.start.isoformat() if self.start else None,
               "end": self.end.isoformat() if self.end else None, "fill_model": self.fill_model.version,
               "engine": ENGINE_VERSION}
        if self.split_mark or self.warmup:
            out.update(split_mark=bool(self.split_mark), warmup=int(self.warmup))
        return out


# --------------------------------------------------------------------------- one day of data
class History:
    """Each root's prior sessions (open, high, low, close), oldest first, as the run moves on."""

    def __init__(self, depth: int):
        self.depth = max(0, int(depth))
        self.rows: dict[str, list[tuple[float, float, float, float]]] = {}

    def add(self, root: str, prices: np.ndarray) -> bool:
        """Add one session (True when it had a price to add)."""
        p = prices[np.isfinite(prices)]
        if p.size == 0 or self.depth == 0:
            return False
        rows = self.rows.setdefault(root, [])
        rows.append((float(p[0]), float(p.max()), float(p.min()), float(p[-1])))
        del rows[:-self.depth]
        return True

    def arrays(self, root: str, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rows = self.rows.get(root, [])[-n:] if n > 0 else []
        if not rows:
            empty = np.zeros(0)
            return empty, empty, empty, empty
        a = np.array(rows, dtype=np.float64)
        return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


class GreekBlocks:
    """One root-day's implied vols and greeks, computed in blocks: when a program first reads a greek
    at minute i, the engine solves those contracts (and their neighbours: the same expiries, strikes
    within a margin) at minute i AND the batch's next `block` decision minutes in one vectorized call,
    so numpy's per-call cost is paid once per block instead of once per minute. The later minutes'
    values stay in this cache until their own minute: a program at minute i is handed row i only."""

    def __init__(self, chain: "DayChain", rate: float, close_minute: int, wanted: Sequence[int], block: int = 30):
        self.chain = chain
        self.rate = rate
        self.close_minute = close_minute
        self.wanted = np.array(sorted(set(int(m) for m in wanted)), dtype=np.int64)
        self.block = int(block)
        shape = chain.bid.shape
        self.values = np.full((5,) + shape, np.nan, dtype=np.float64)
        self.done = np.zeros(shape, dtype=bool)

    def get(self, mi: int, idx: np.ndarray) -> tuple[np.ndarray, ...]:
        need = idx[~self.done[mi, idx]]
        if need.size:
            self._solve(mi, need)
        v = self.values[:, mi, idx]
        return v[0], v[1], v[2], v[3], v[4]

    def _solve(self, mi: int, need: np.ndarray) -> None:
        chain = self.chain
        later = self.wanted[self.wanted > mi][: self.block - 1]
        cols = np.concatenate(([mi], later)).astype(np.int64)
        spot_row = chain.underlying.price[cols]
        spot = float(chain.underlying.price[mi]) if np.isfinite(chain.underlying.price[mi]) else float(np.nanmean(spot_row))
        pad = 0.02 * spot if np.isfinite(spot) else 0.0
        near = np.isin(chain.dte, np.unique(chain.dte[need])) & (chain.strike >= chain.strike[need].min() - pad) & \
            (chain.strike <= chain.strike[need].max() + pad)
        rows = np.union1d(np.flatnonzero(near), need)
        bid = chain.bid[np.ix_(cols, rows)]
        ask = chain.ask[np.ix_(cols, rows)]
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(bid) & np.isfinite(ask) & (ask > 0) & (bid >= 0) & (ask >= bid) & np.isfinite(spot_row)[:, None]
        r_idx, c_idx = np.nonzero(ok)            # r_idx indexes cols, c_idx indexes rows
        if r_idx.size:
            minute = chain.open_min + cols[r_idx]
            contract = rows[c_idx]
            mid = 0.5 * (bid[r_idx, c_idx] + ask[r_idx, c_idx])
            s = spot_row[r_idx]
            years = G.years_to_expiry(chain.dte[contract], minute, close_minute=self.close_minute)
            iv = G.implied_vol(mid, s, chain.strike[contract], years, self.rate, chain.is_call[contract])
            d, g, t, v = G.greeks(s, chain.strike[contract], years, self.rate, iv, chain.is_call[contract])
            for k, arr in enumerate((iv, d, g, t, v)):
                self.values[k, cols[r_idx], contract] = arr
        self.done[np.ix_(cols, rows)] = True


class DayClosed(RuntimeError):
    """A closed day (`DayData.close`) was read. Its chains are gone: answering "no chain" would settle every expiring
    position as `expired_without_data`, so a read after the close is a bug, and says so."""


class _ClosedChains:
    """What a closed day's `chains` becomes: any use of it raises `DayClosed` (never an empty mapping)."""

    def __init__(self, day: dt.date):
        self.day = day

    def _refuse(self, *args: Any, **kwargs: Any) -> Any:
        raise DayClosed(f"the replay's day {self.day} is closed: its chains were freed")

    get = __getitem__ = __contains__ = __iter__ = __len__ = items = keys = values = _refuse


class DayData:
    """One trading day: each root's chain once, and one shared snapshot per root and minute."""

    def __init__(self, store: "Store", day: dt.date, roots: Sequence[str], events: EventCalendar, history: History,
                 ordinal: int, *, split_eve: Mapping[str, float] | None = None):
        self.day = day
        self.store = store
        self.ordinal = ordinal
        #: {root: factor} for each root whose next replayed session is a stock split (`split_eves`): today is its eve.
        self.split_eve: dict[str, float] = dict(split_eve or {})
        self.weekday = day.weekday()
        self.open_min, self.close_min = store.session(day)
        self.minutes = self.close_min - self.open_min + 1
        self.rate = rate_on(day)
        self.chains: dict[str, "DayChain"] = {}
        for root in roots:
            if store.has("nbbo", root, day) and store.has("underlying", root, day):
                self.chains[root] = store.chain(root, day)
        self.rules = {root: venue.rules_for(root, open_minute=self.open_min, close_minute=self.close_min) for root in roots}
        self.rules_rows = {root: r.as_dict() for root, r in self.rules.items()}
        self.events = events.flags(day)
        self.events_next = events.flags(events.next_day(day))
        self.history = history
        self._snaps: dict[tuple[str, int], Snapshot] = {}
        self._blocks: dict[str, GreekBlocks] = {}
        self._wanted: dict[str, set[int]] = {}
        self._unders: dict[tuple[str, int, int], Any] = {}
        self._minute = -1
        self.closed = False

    def want(self, root: str, minutes: Any) -> None:
        """Minutes some program decides on (the greek blocks cover these)."""
        self._wanted.setdefault(root, set()).update(int(m) for m in minutes)

    def _check_open(self) -> None:
        if self.closed:
            raise DayClosed(f"the replay's day {self.day} is closed: its snapshots, greek blocks and chains were freed")

    def blocks(self, root: str) -> "GreekBlocks | None":
        self._check_open()
        found = self._blocks.get(root)
        if found is None and root in self.chains:
            found = self._blocks[root] = GreekBlocks(self.chains[root], self.rate, self.close_min, sorted(self._wanted.get(root, ())))
        return found

    def advance(self, mi: int) -> None:
        """Drop the caches of earlier minutes."""
        if mi != self._minute:
            self._drop_snapshots()
            self._unders.clear()
            self._minute = mi

    def _drop_snapshots(self) -> None:
        # Each snapshot a program decided on caches its ChainView, which points back at the snapshot: a
        # reference cycle. Left alone, every such snapshot, and through its greeks source the root-day's
        # GreekBlocks and DayChain (the day's [minute, contract] grids), lives until a FULL collection,
        # which comes rarer as the run's long-lived objects (trades, fills) grow: a worker's memory grew
        # with the days of its segment. Breaking the cycle frees them by reference count, at once.
        for snap in self._snaps.values():
            snap.release()
        self._snaps.clear()

    def close(self) -> None:
        """The day is over: drop its snapshots, greek blocks and chains, so the next day loads with this
        one's grids already freed (`run` calls it last thing each day). A closed day refuses every read
        (`DayClosed`): `snapshot`, `blocks`, `under` and its `chains` raise rather than answer "no data"."""
        self._drop_snapshots()
        self._unders.clear()
        self._blocks.clear()
        self.chains = _ClosedChains(self.day)  # type: ignore[assignment]
        self.closed = True

    def snapshot(self, root: str, mi: int) -> Snapshot | None:
        self._check_open()
        key = (root, mi)
        found = self._snaps.get(key)
        if found is not None:
            return found
        chain = self.chains.get(root)
        if chain is None:
            return None
        blocks = self.blocks(root)
        snap = Snapshot(root, self.open_min + mi, float(chain.underlying.price[mi]), chain.dte, chain.strike, chain.is_call,
                        chain.bid[mi], chain.ask[mi], chain.bid_size[mi], chain.ask_size[mi], oi=chain.oi, rate=self.rate,
                        close_minute=self.close_min, keys=chain.key, clean=True,
                        greeks_source=(lambda idx, _mi=mi, _b=blocks: _b.get(_mi, idx)) if blocks is not None else None)
        self._snaps[key] = snap
        return snap

    def under(self, root: str, mi: int, history: int):
        self._check_open()
        key = (root, mi, history)
        found = self._unders.get(key)
        if found is None:
            chain = self.chains[root]
            opens, highs, lows, closes = self.history.arrays(root, history)
            found = underlying_view(root, chain.underlying.price[: mi + 1], closes=closes, opens=opens, highs=highs, lows=lows)
            self._unders[key] = found
        return found

    def regime(self, root: str) -> dict[str, float]:
        """The day's regime features (engine-side, for the results' terciles): the realized vol of
        the prior ten sessions and the at-the-money implied vol at 10:00 of the nearest expiry; and,
        for the results' drift block, the day's overnight return `ret_on` (its first price over the
        root's last session's close in the history, which holds earlier sessions only), its intraday
        return `ret_in` (last price over first) and `session` (the minutes between them), `ret`, close
        to close, and `rv_day`, the day's own realized variance (the sum of its squared one-minute log
        returns: the drift fit's weights). A program never sees any of them."""
        out = {"rv": math.nan, "iv": math.nan, "ret": math.nan, "ret_on": math.nan, "ret_in": math.nan, "session": math.nan,
               "rv_day": math.nan}
        opens, highs, lows, closes = self.history.arrays(root, 11)
        if closes.size >= 3:
            r = np.diff(np.log(closes))
            out["rv"] = float(np.std(r, ddof=1) * math.sqrt(252.0))
        chain = self.chains.get(root)
        known = np.flatnonzero(np.isfinite(chain.underlying.price)) if chain is not None else np.zeros(0, dtype=np.int64)
        if known.size:
            first, last = float(chain.underlying.price[known[0]]), float(chain.underlying.price[known[-1]])
            out["ret_in"] = last / first - 1.0 if first > 0 else math.nan
            out["session"] = float(known[-1] - known[0])
            path = chain.underlying.price[known]
            if known.size >= 2 and bool(np.all(path > 0)):
                out["rv_day"] = float(np.sum(np.diff(np.log(path)) ** 2))
            if closes.size and closes[-1] > 0:
                out["ret"] = last / float(closes[-1]) - 1.0
                out["ret_on"] = first / float(closes[-1]) - 1.0
        mi = min(30, self.minutes - 2)
        snap = self.snapshot(root, mi)
        if snap is not None and np.isfinite(snap.spot):
            pool = np.flatnonzero(snap.valid)
            if pool.size:
                first = int(snap.dte[pool].min())
                pool = pool[snap.dte[pool] == first]
                near = pool[np.argsort(np.abs(snap.strike[pool] - snap.spot))[:4]]
                iv = snap.greeks_for(near)[0]
                if np.isfinite(iv).any():
                    out["iv"] = float(np.nanmean(iv))
        return out


# --------------------------------------------------------------------------- one program's account
@dataclass
class Position:
    pid: int
    type: str
    root: str
    legs: tuple[L.LegFill, ...]
    keys: np.ndarray
    expirations: np.ndarray       # expiration day ordinal of each leg
    qty: int
    opened_qty: int
    entry: float                  # value a share (average over the open's fills)
    max_loss_share: float
    collateral: float
    opened_day: int               # ordinal
    opened_mi: int
    opened_session: int
    info: dict
    tag: str = ""
    note: str = ""
    cash: float = 0.0             # every cash flow of this trade, fees included
    fees: float = 0.0
    exit_value_qty: float = 0.0   # sum of exit value x quantity closed
    exit_day: int = 0
    exit_mi: int = 0
    reason: str = ""
    idx: np.ndarray | None = None  # today's snapshot index of each leg (-1: not in today's chain)
    last_mark: float = math.nan
    closing: int = 0              # working close order id (0: none)
    range_: tuple[float, float] | None = field(default=None, repr=False, compare=False)   # `bounds()`, once

    @property
    def credit(self) -> bool:
        return self.type in L.CREDIT

    def bounds(self) -> tuple[float, float]:
        """What the package can be worth a share at expiry (`legs.value_bounds`), from its legs' own expirations."""
        if self.range_ is None:
            self.range_ = L.value_bounds(self.legs, [int(e) for e in self.expirations])
        return self.range_

    def legs_today(self) -> tuple[L.LegFill, ...]:
        return tuple(L.LegFill(int(i), leg.key, leg.side, leg.ratio, leg.dte, leg.strike, leg.is_call)
                     for leg, i in zip(self.legs, self.idx))


@dataclass
class Working:
    oid: int
    order: L.Order
    remaining: int
    placed_mi: int
    arrival_mi: int
    expires_mi: int | None
    reserve_left: float
    pid: int = 0                  # the position an open creates / a close closes
    forced: bool = False          # the venue's liquidation
    filled: int = 0
    seen: bool = False            # met a two-sided quote at least once
    aggressive: bool = False      # marketable when it first met one: its remainder keeps taking the natural
    range_: tuple[float, float] | None = field(default=None, repr=False, compare=False)   # an open's package bounds, once


#: A forced close's order note -> the trade's exit reason (the note survives the shadow book's saved state).
FORCED_REASONS = {"expiry close": "expiry_close", "liquidation": "liquidated"}


class Account:
    """One program in one run: its runner, cash, positions, orders and the record."""

    def __init__(self, program: Program, cfg: RunConfig, roots: tuple[str, ...]):
        self.program = program
        self.cfg = cfg
        self.roots = roots
        self.needs = program.needs
        self.runner = program.start(timeout=cfg.timeout, max_errors=cfg.max_errors, budget_seconds=cfg.max_decide_seconds)
        #: The run's own copy: a program that mutates a list in ctx.params changes it for this run only.
        self.params = copy.deepcopy(program.params)
        self.cash = float(cfg.capital)
        self.equity_prev = float(cfg.capital)
        self.positions: dict[int, Position] = {}
        self.orders: dict[int, Working] = {}
        self.next_id = 1
        self.trades: list[dict] = []
        self.daily: list[tuple[str, float, float]] = []
        self.fill_rows: list[tuple[str, float, float, bool]] = []  # (action, slip a share, slip in half-spreads, at natural)
        #: bounded_close: closes (a program's, the House's, the window's end) filled at the package's least because the
        #: legs' touches added up to less (`_in_bounds`); blocked_out_of_range: order-minutes held back because the
        #: legs' touches added up to a price the package can never trade at (`_tradeable`).
        self.counts = {"orders": 0, "opens": 0, "closes": 0, "filled": 0, "partial_fills": 0, "cancelled": 0, "expired": 0,
                       "rejected": 0, "liquidated": 0, "settled": 0, "exercised": 0, "fills": 0, "bounded_close": 0,
                       "blocked_out_of_range": 0}
        self.reject_reasons: dict[str, int] = {}
        self.pending_shares: list[tuple[Position, str, float, float]] = []  # (trade, root, shares, reference price)
        self.closed_since: list[dict] = []
        self.rejects_since: list[str] = []
        self.orders_today = 0
        self.session = 0
        self.warming = False          # replaying warm-up days: decide runs, its intents are dropped
        self.liquidity_at: tuple[int, int] | None = None   # the minute `liquidity_used` counts
        self.liquidity_used: dict[int, int] = {}           # contract key -> contracts passive fills took this minute
        #: The hours it held exposure (the results' drift block, Train runs only): ISO day -> root -> (1 when held from the
        #: prior close, the minutes held after the first price, the root's return over the hours held). `_held` is today's
        #: interval per holding: key -> [root, start minute index (-1: the prior close; None: not opened today), end minute
        #: index (None: not ended yet)].
        self.exposure: dict[str, dict[str, tuple[int, float, float]]] = {}
        self._held: dict[Any, list] = {}

    # ------------------------------------------------------------------ helpers
    def _id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def _reject(self, why: str, *, tell: bool = True) -> None:
        self.counts["rejected"] += 1
        key = why.split(":")[0][:80]
        self.reject_reasons[key] = self.reject_reasons.get(key, 0) + 1
        if tell and len(self.rejects_since) < 20:
            self.rejects_since.append(why[:200])

    def buying_power(self) -> float:
        held = sum(p.collateral * venue.MULTIPLIER * p.qty for p in self.positions.values() if p.credit)
        working = sum(w.reserve_left for w in self.orders.values() if w.order.action == "open")
        return self.cash - held - working

    def equity(self) -> float:
        return self.cash + sum((p.last_mark if math.isfinite(p.last_mark) else p.entry) * venue.MULTIPLIER * p.qty
                               for p in self.positions.values())

    def decision_minutes(self, day: DayData) -> set[int]:
        first = max(self.needs.start, day.open_min + 1) - day.open_min
        last = min(self.needs.end - day.open_min, day.minutes - 3)
        return set(range(first, last + 1, self.needs.cadence)) if first <= last else set()

    def _hold(self, key: Any, root: str, start: int | None = None, end: int | None = None) -> None:
        """Widen today's interval of one holding (`key`: a position's id, or its exercised shares'): its earliest start
        (-1: from the prior close), its latest end. Train runs only: the drift block is Train's, and a live account's day
        (the shadow book's `LiveDay`) has none of what `_exposure` reads."""
        if getattr(self.cfg, "window", "train") != "train":
            return
        span = self._held.setdefault(key, [root, None, None])
        if start is not None:
            span[1] = start if span[1] is None else min(span[1], start)
        if end is not None:
            span[2] = end if span[2] is None else max(span[2], end)

    def _exposure(self, day: DayData) -> None:
        """Today's `exposure` per root from its holdings' intervals, merged where they overlap: an interval that began
        before today starts at the prior close (a carried position, or exercised shares that gapped to the open), one that
        did not end is held to the close. A root's return over the hours held is the product of its merged intervals'
        returns and its minutes their sum, so a position closed in the morning and one opened in the afternoon are two
        intervals, never the whole day. Train runs only (`_hold`)."""
        if getattr(self.cfg, "window", "train") != "train" or not self._held:
            return
        arrays = getattr(day.history, "arrays", None)
        by_root: dict[str, list[tuple[int, int | None]]] = {}
        for root, begin, end in self._held.values():
            by_root.setdefault(root, []).append((-1 if begin is None else int(begin), end))
        out: dict[str, tuple[int, float, float]] = {}
        for root, spans in by_root.items():
            chain = day.chains.get(root)
            price = chain.underlying.price if chain is not None else np.zeros(0)
            known = np.flatnonzero(np.isfinite(price))
            if not known.size:
                continue
            first, last = int(known[0]), int(known[-1])
            closes = arrays(root, 1)[3] if callable(arrays) else np.zeros(0)
            prior = float(closes[-1]) if closes.size and float(closes[-1]) > 0 else None
            merged: list[list[int]] = []
            for begin, end in sorted((b, last if e is None else int(e)) for b, e in spans):
                if merged and begin <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([begin, end])
            growth, minutes, carried = 1.0, 0.0, 0
            for begin, end in merged:
                from_close = begin < 0 and prior is not None
                a = first if begin < first else min(begin, last)
                b = max(a, min(end, last))
                at_start = prior if from_close else float(price[known[known <= a][-1]])
                growth *= float(price[known[known <= b][-1]]) / at_start
                minutes += float(b - a)
                carried |= 1 if from_close else 0
            out[root] = (carried, minutes, growth - 1.0)
        if out:
            self.exposure[day.day.isoformat()] = out

    # ------------------------------------------------------------------ the day
    def begin_day(self, day: DayData) -> None:
        self.orders_today = 0
        self._held = {}
        for pos, root, shares, ref in self.pending_shares:
            self._hold(("shares", pos.pid), root, -1, 0)  # exercised shares: held from the prior close to the open's gap
            chain = day.chains.get(root)
            price = chain.underlying.price if chain is not None else np.zeros(0)
            first = price[np.isfinite(price)]
            gap = float(shares) * ((float(first[0]) if first.size else ref) - ref)
            self.cash += gap
            pos.cash += gap
            pos.info["share_gap"] = round(gap, 2)
            self._finish(pos, day)
        self.pending_shares = []
        for pos in self.positions.values():
            self._hold(pos.pid, pos.root, -1)  # carried from the prior close
            chain = day.chains.get(pos.root)
            pos.idx = chain.index_of(pos.keys) if chain is not None else np.full(len(pos.legs), -1)
        for pos in list(self.positions.values()):
            if int(pos.expirations.min()) < day.ordinal:
                self._settle_missed(day, pos)      # its expiry fell on a day the run did not replay

    def step(self, day: DayData, mi: int, decide: bool) -> None:
        if self.orders:
            self._work(day, mi)
        self._venue(day, mi)
        if decide and not self.runner.disqualified:
            self._decide(day, mi)

    def _work(self, day: DayData, mi: int) -> None:
        for oid in sorted(self.orders):
            work = self.orders.get(oid)
            if work is None or mi < work.arrival_mi:
                continue
            if work.expires_mi is not None and mi > work.expires_mi:
                self._drop(work, "expired")
                continue
            self._try_fill(day, mi, work)

    def _try_fill(self, day: DayData, mi: int, work: Working) -> None:
        order = work.order
        snap = day.snapshot(order.root, mi)
        if snap is None:
            return
        if order.action == "close":
            pos = self.positions.get(work.pid)
            if pos is None:
                self._drop(work, "cancelled")
                return
            legs = pos.legs_today()
            if any(leg.idx < 0 for leg in legs):
                return
            lo, hi = pos.bounds()
        else:
            legs = order.legs
            # An open works the day it was decided (`end_day` drops every order), so its legs' dte are today's.
            if work.range_ is None:
                work.range_ = L.value_bounds(legs, [day.ordinal + int(leg.dte) for leg in legs])
            lo, hi = work.range_
        stress = self.cfg.stress
        natural, cap = L.natural_value(snap, legs, order.action, stress=stress)
        if not math.isfinite(natural):
            return
        mid = L.mid_value(snap, legs)
        opening = order.action == "open"
        # The UNSTRESSED natural: stress changes what a fill costs, never which limits can fill (a limit behind the
        # touch stays behind it) or which minutes are a market at all.
        plain = natural if stress == 1.0 else L.natural_value(snap, legs, order.action)[0]
        if not self._tradeable(plain, lo, hi, opening):
            # The legs' touches add up to a price the package can never trade at: nothing fills this minute, and the
            # order keeps working. When this is its first look, the minute tells nothing about the market, so the
            # order is judged against the natural it was decided on: one marketable there is a taker (it takes the
            # next real natural, as on a normal arrival), a patient one rests at its own limit. A blocked minute
            # never turns a patient order into a taker, nor a taker into an order that sells at a limit far through
            # the market.
            self.counts["blocked_out_of_range"] += 1
            if not work.seen:
                decided = order.natural
                taker = math.isfinite(decided) and (decided <= order.limit + 1e-9 if opening else decided >= order.limit - 1e-9)
                work.seen, work.aggressive = True, taker
            return
        if work.forced:
            price, qty = natural, work.remaining
        else:
            marketable = natural <= order.limit + 1e-9 if opening else natural >= order.limit - 1e-9
            if not work.seen:
                work.seen, work.aggressive = True, marketable
            room = None
            if marketable:
                # A taking order (and its remainder after a size-capped fill) takes the natural, the
                # better of it and the limit; a resting order the market later comes through fills at
                # its own limit.
                price = natural if work.aggressive else order.limit
            else:
                span = plain - mid
                q = (order.limit - mid) / span if abs(span) > 1e-12 else 1.0
                shape = [(int(snap.dte[leg.idx]), leg.strike / snap.spot - 1.0 if np.isfinite(snap.spot) else math.nan)
                         for leg in legs]
                model = self.cfg.fill_model
                p = model.p(order.root, q, shape, snap.minute)
                if stress > 1.0:
                    p *= F.STRESS_HAZARD  # a stress run also asks: does it survive patient orders filling half as often?
                if p <= 0.0 or not self._adverse(day, mi, order.root, legs, mid, opening):
                    return
                if F.draw([leg.key for leg in legs], day.ordinal, snap.minute, "buy" if opening else "sell") >= p:
                    return
                # The passive liquidity of this minute: what Train's fills at this level found beyond the
                # queue, per contract, shared by every order of this program on that contract.
                if self.liquidity_at != (day.ordinal, mi):
                    self.liquidity_at, self.liquidity_used = (day.ordinal, mi), {}
                sizes = model.sizes(order.root, q, shape, [leg.ratio for leg in legs])
                room = min((size - self.liquidity_used.get(leg.key, 0)) // leg.ratio for leg, size in zip(legs, sizes))
                price = order.limit
                if stress > 1.0:
                    # Stress charges a passive fill too: (stress - 1) x the structure's half-spread. A narrowed
                    # spread (stress below 1, the robustness run at the mid) never fills a limit better than itself.
                    extra = (stress - 1.0) * abs(plain - mid)
                    price = price + extra if opening else price - extra
        bounded = self._in_bounds(price, lo, hi, opening)
        if bounded is None:
            self.counts["blocked_out_of_range"] += 1
            return
        floored = bounded != price
        price = bounded
        if not work.forced:
            qty = min(work.remaining, cap) if room is None else min(work.remaining, cap, room)
            if qty <= 0:
                return
            if room is not None:
                for leg in legs:
                    self.liquidity_used[leg.key] = self.liquidity_used.get(leg.key, 0) + qty * leg.ratio
        leg_prices = []
        for leg in legs:
            buying = (leg.side > 0) == opening
            leg_prices.append(float(snap.ask[leg.idx] if buying else snap.bid[leg.idx]))
        fees = L.order_fees(order.root, legs, leg_prices, qty, order.action)
        if floored:
            # A close held at the package's least has no market price to measure slippage against (its mid is the
            # blown-out quote's): it is counted here and flagged on its trade, never as price improvement over the mid.
            self.counts["bounded_close"] += 1
            self.positions[work.pid].info["bounded"] = True
        else:
            half = abs(natural - mid)
            slip = (price - mid) if opening else (mid - price)
            self.fill_rows.append((order.action, slip, slip / half if half > 1e-12 else 0.0, abs(price - natural) < 1e-9))
        self.counts["fills"] += 1
        if opening:
            self._open_fill(day, mi, work, price, qty, fees)
        else:
            self._close_fill(day, mi, work, price, qty, fees,
                             FORCED_REASONS.get(work.order.note, "liquidated") if work.forced else "program")
        work.remaining -= qty
        work.filled += qty
        if work.order.action == "open":
            work.reserve_left = work.order.reserve * work.remaining / max(1, work.order.qty)
        if work.remaining <= 0:
            self.counts["filled"] += 1
            self._drop(work, None)
        elif work.filled == qty:
            self.counts["partial_fills"] += 1

    @staticmethod
    def _tradeable(natural: float, lo: float, hi: float, opening: bool) -> bool:
        """Whether this minute's natural is a price the package [lo, hi] (`legs.value_bounds`) can trade at: an open's
        inside the range (above the least, strictly: a vertical bought for 0.00 would be free), a close's at or below
        the most (below the least it still trades, at the least: `_in_bounds`). Outside, nothing fills that minute."""
        if natural > hi + 1e-9:
            return False
        return not opening or natural > lo + 1e-9

    @staticmethod
    def _in_bounds(price: float, lo: float, hi: float, opening: bool) -> float | None:
        """A package trades only inside what it can be worth at expiry, [lo, hi] (`legs.value_bounds`). Its legs'
        touches can add up to a price outside that range when a leg's quote blows out (an index leg in the money quoted
        with no bid and a far ask, the minute of an FOMC release, the last minutes of an expiry): the natural close
        of a 5-wide debit vertical can then be -30, a loss many times the most the vertical can lose. No one sells a
        package for less than it can ever be worth or buys it for more (complex-order price checks exist to refuse it), so:
        an open at or below the package's least (a free package) or above its most, or a close that would RECEIVE more
        than its most, does not fill this minute (it keeps working); a close that would receive LESS than the package's
        least fills at that least, so a close never loses more than the maximum loss. None: no fill.

        The floor is honest because it is the live path's own: `league/live/step.py` `OptionsLive._send_close` (the
        lines after "A close's limit stays one the gateway takes") never sends a close below 0 for a debit structure,
        below -(collateral - 0.01) for a credit one, or below a tick for a long call or put. Each of those is at or
        above this least, so a real close never sells for less than the Gym's floor, and one that does not fill keeps a
        package worth at least that least (`test_live_parity.LiveCloseFloor` pins it for each bounded structure type)."""
        if price > hi + 1e-9:
            return None
        if opening:
            return price if price > lo + 1e-9 else None
        return max(price, lo)

    @staticmethod
    def _adverse(day: DayData, mi: int, root: str, legs: Sequence[L.LegFill], mid: float, buying: bool) -> bool:
        """Adverse selection: a passive order is filled by someone who wants the other side, so it never
        fills on a minute after which the structure moves in its favour (a buyer is not filled just
        before the mid rises; a seller not just before it falls). The engine reads the NEXT minute's
        quotes to decide this; the program never sees them."""
        chain = day.chains.get(root)
        nxt = mi + 1
        if chain is None or nxt >= day.minutes:
            return False
        value = 0.0
        for leg in legs:
            bid, ask = float(chain.bid[nxt, leg.idx]), float(chain.ask[nxt, leg.idx])
            if not (math.isfinite(bid) and math.isfinite(ask)):
                return False
            value += leg.side * leg.ratio * 0.5 * (bid + ask)
        return value <= mid + 1e-9 if buying else value >= mid - 1e-9

    def _open_fill(self, day: DayData, mi: int, work: Working, price: float, qty: int, fees: float) -> None:
        order = work.order
        cash = -price * venue.MULTIPLIER * qty - fees
        self.cash += cash
        pos = self.positions.get(work.pid) if work.pid else None
        if pos is None:
            pid = self._id()
            work.pid = pid
            snap_legs = order.legs
            keys = np.array([leg.key for leg in snap_legs], dtype=np.int64)
            pos = Position(
                pid=pid, type=order.type, root=order.root, legs=snap_legs, keys=keys,
                expirations=np.array([day.ordinal + leg.dte for leg in snap_legs], dtype=np.int64), qty=0, opened_qty=0,
                entry=price, max_loss_share=L.max_loss_share(order.type, price, order.collateral) if self._defined(order, price) else order.max_loss_share,
                collateral=order.collateral, opened_day=day.ordinal, opened_mi=mi, opened_session=self.session,
                info={**order.extra, "filled_minute": day.open_min + mi}, tag=order.tag, note=order.note,
                idx=np.array([leg.idx for leg in snap_legs], dtype=np.int64))
            self.positions[pid] = pos
        else:
            total = pos.opened_qty + qty
            pos.entry = (pos.entry * pos.opened_qty + price * qty) / total
            pos.max_loss_share = L.max_loss_share(pos.type, pos.entry, pos.collateral) if self._defined(order, pos.entry) else pos.max_loss_share
        pos.qty += qty
        pos.opened_qty += qty
        pos.cash += cash
        pos.fees += fees
        pos.last_mark = pos.entry if not math.isfinite(pos.last_mark) else pos.last_mark
        self._hold(pos.pid, pos.root, mi)

    @staticmethod
    def _defined(order: L.Order, value: float) -> bool:
        try:
            L.max_loss_share(order.type, value, order.collateral)
            return True
        except L.Refused:
            return False

    def _close_fill(self, day: DayData, mi: int, work: Working, price: float, qty: int, fees: float, reason: str) -> None:
        pos = self.positions[work.pid]
        cash = price * venue.MULTIPLIER * qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += price * qty
        pos.qty -= qty
        if pos.qty <= 0:
            pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, mi, reason
            if reason in FORCED_REASONS.values():
                self.counts["liquidated"] += 1
            self._finish(pos, day)

    def _finish(self, pos: Position, day: DayData) -> None:
        self._hold(pos.pid, pos.root, None, pos.exit_mi if pos.exit_day == day.ordinal else 0)
        self.positions.pop(pos.pid, None)
        if pos.closing:
            self.orders.pop(pos.closing, None)
        self.trades.append(self._trade_row(pos))
        self.closed_since.append({"id": pos.pid, "type": pos.type, "root": pos.root, "pnl": round(pos.cash, 2),
                                  "reason": pos.reason, "tag": pos.tag})

    def _trade_row(self, pos: Position) -> dict:
        from .day import from_ordinal

        max_loss = pos.max_loss_share * venue.MULTIPLIER * pos.opened_qty
        exit_value = pos.exit_value_qty / pos.opened_qty if pos.opened_qty else math.nan
        return {
            "id": pos.pid, "root": pos.root, "type": pos.type, "tag": pos.tag, "qty": pos.opened_qty,
            "legs": [{"dte": leg.dte, "strike": leg.strike, "right": "C" if leg.is_call else "P",
                      "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio} for leg in pos.legs],
            "day": from_ordinal(pos.opened_day).isoformat(), "entry_minute": pos.info.get("minute"),
            "filled_minute": pos.info.get("filled_minute"),
            "exit_day": from_ordinal(pos.exit_day).isoformat() if pos.exit_day else None,
            "exit_minute": pos.exit_mi + pos.info.get("open_min", 570) if pos.exit_mi else None,
            "sessions_held": self.session - pos.opened_session,
            "entry": round(pos.entry, 4), "exit": None if not math.isfinite(exit_value) else round(exit_value, 4),
            "max_loss": round(max_loss, 2), "fees": round(pos.fees, 2), "pnl": round(pos.cash, 2),
            "return_on_max_loss": round(pos.cash / max_loss, 4) if max_loss > 0 else None,
            "exit_reason": pos.reason, "context": pos.info.get("context", {}), "note": pos.note,
            # Its exit was set by the package's range, not by this minute's market: a close filled at the package's
            # least, or an exit at the last price the package traded at because the latest quote left its range
            # (`_in_bounds`, `_fallback_close`).
            "bounded": bool(pos.info.get("bounded")),
        }

    def _drop(self, work: Working, why: str | None) -> None:
        self.orders.pop(work.oid, None)
        if work.order.action == "close":
            pos = self.positions.get(work.pid)
            if pos is not None and pos.closing == work.oid:
                pos.closing = 0
        if why == "expired":
            self.counts["expired"] += 1
        elif why == "cancelled":
            self.counts["cancelled"] += 1

    # ------------------------------------------------------------------ the venue
    def _venue(self, day: DayData, mi: int) -> None:
        minute = day.open_min + mi
        for root in self.roots:
            rules = day.rules.get(root)
            if rules is None:
                continue
            if minute == rules.open_cutoff:
                for work in list(self.orders.values()):
                    if work.order.action == "open" and work.order.root == root and any(leg.dte == 0 for leg in work.order.legs):
                        self._drop(work, "cancelled")
            if minute == rules.close_cutoff:
                for work in list(self.orders.values()):
                    pos = self.positions.get(work.pid)
                    if work.order.action == "close" and not work.forced and pos is not None and pos.root == root and \
                            int(pos.expirations.min()) == day.ordinal:
                        self._drop(work, "cancelled")
            house = rules.expiry_close is not None and rules.expiry_close <= minute < rules.close_cutoff
            liquidating = rules.liquidation is not None and minute >= rules.liquidation
            if not (house or liquidating):
                continue
            for pos in list(self.positions.values()):
                if pos.root != root or int(pos.expirations.min()) != day.ordinal or pos.pid not in self.positions:
                    continue
                if pos.closing and self.orders.get(pos.closing) is not None and self.orders[pos.closing].forced:
                    continue
                if not (self._house_closes(day, mi, pos, rules) if house else self._near_money(day, mi, pos, rules)):
                    continue  # left to expire (every expiring leg further out of the money; a long single with no bid)
                if pos.closing and self.orders.get(pos.closing) is not None:
                    self._drop(self.orders[pos.closing], "cancelled")
                order = L.Order("close", pos.type, root, pos.legs_today(), pos.qty, math.nan, math.nan, math.nan, 0.0,
                                0.0, 0.0, 0.0, None, pos.tag, "expiry close" if house else "liquidation", position=pos.pid)
                work = Working(self._id(), order, pos.qty, mi, mi, None, 0.0, pid=pos.pid, forced=True)
                self.orders[work.oid] = work
                pos.closing = work.oid
                self._try_fill(day, mi, work)

    @classmethod
    def _house_closes(cls, day: DayData, mi: int, pos: Position, rules: venue.Rules) -> bool:
        """The House's expiry close (the live path's `_expiry_close`): a leg in or near the money, and a LONG CALL or
        PUT whatever its moneyness while it has a bid or no quote to tell (an exercise would bring 100 shares the
        account cannot carry)."""
        if pos.type in ("long_call", "long_put"):
            snap = day.snapshot(pos.root, mi)
            i = int(pos.idx[0]) if pos.idx is not None else -1
            bid = float(snap.bid[i]) if snap is not None and i >= 0 else math.nan
            if not math.isfinite(bid) or bid > 0:
                return True
        return cls._near_money(day, mi, pos, rules)

    @staticmethod
    def _near_money(day: DayData, mi: int, pos: Position, rules: venue.Rules) -> bool:
        """A leg expiring today is in the money or within `rules.near_money_share` of it at minute mi (or
        there is no price to tell): the live path's `_expiry_close` predicate."""
        snap = day.snapshot(pos.root, mi)
        spot = snap.spot if snap is not None else math.nan
        return any(venue.near_money(leg.strike, leg.is_call, spot, rules.near_money_share)
                   for leg, exp in zip(pos.legs, pos.expirations) if int(exp) == day.ordinal)

    # ------------------------------------------------------------------ decisions
    def _position_rows(self, day: DayData, mi: int) -> list[dict]:
        rows = []
        for pos in self.positions.values():
            snap = day.snapshot(pos.root, mi)
            legs = pos.legs_today()
            mark = natural = math.nan
            if snap is not None and all(leg.idx >= 0 for leg in legs):
                mark = L.mid_value(snap, legs)
                natural = L.natural_value(snap, legs, "close")[0]
                if math.isfinite(mark):
                    # The account's mark (equity, a mark exit) is a mid inside the package's range (`_set_mark`); the
                    # program's row keeps the raw mid and natural, as the live path's rows do.
                    self._set_mark(pos, mark)
            leg_rows = [{"id": int(leg.idx), "dte": int(exp - day.ordinal), "strike": leg.strike, "is_call": leg.is_call,
                         "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio}
                        for leg, exp in zip(legs, pos.expirations)]
            held = (self.session - pos.opened_session) * 390 + mi - pos.opened_mi
            rows.append(position_row(pid=pos.pid, type_=pos.type, root=pos.root, qty=pos.qty, legs=leg_rows, entry=pos.entry,
                                     max_loss=pos.max_loss_share * venue.MULTIPLIER * pos.qty, mark=mark, natural=natural,
                                     held_minutes=held, held_days=self.session - pos.opened_session, tag=pos.tag))
        return rows

    def _order_rows(self, day: DayData, mi: int) -> list[dict]:
        return [order_row(oid=w.oid, kind=w.order.action, type_=w.order.type, root=w.order.root, qty=w.order.qty,
                          filled=w.filled, limit=w.order.limit, age_minutes=mi - w.placed_mi, position=w.pid or None,
                          tag=w.order.tag) for w in self.orders.values() if not w.forced]

    def _decide(self, day: DayData, mi: int) -> None:
        chains, unders = {}, {}
        needs = self.needs
        for root in self.roots:
            snap = day.snapshot(root, mi)
            if snap is None:
                continue
            chains[root] = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band),
                                     key=(needs.dte_min, needs.dte_max, needs.band))
            unders[root] = day.under(root, mi, needs.history)
        if not chains:
            return
        positions = self._position_rows(day, mi)
        ctx = build_ctx(minute=day.open_min + mi, open_minute=day.open_min, close_minute=day.close_min, weekday=day.weekday,
                        chains=chains, underlyings=unders, positions=positions, orders=self._order_rows(day, mi),
                        cash=self.cash, equity=self.equity(), budget=self.cfg.capital, buying_power=self.buying_power(),
                        params=self.params, rules={r: day.rules_rows[r] for r in chains}, events=day.events,
                        events_next=day.events_next, closed=self.closed_since, rejects=self.rejects_since,
                        roots=tuple(chains))
        self.closed_since = []
        self.rejects_since = []
        intents = self.runner.decide(ctx)
        if self.warming:
            return  # a warm-up day: the program decides (its STATE moves on) but nothing trades
        for intent in intents:
            try:
                self._intent(day, mi, intent)
            except L.Refused as exc:
                self._reject(str(exc), tell=not isinstance(exc, Unsaid))

    def _intent(self, day: DayData, mi: int, intent: dict) -> None:
        arrival = mi + 1
        minute = day.open_min + arrival
        if "cancel" in intent:
            work = self.orders.get(intent["cancel"]) if isinstance(intent["cancel"], int) else None
            if work is None or work.forced:
                raise L.Refused("cancel: no such working order")
            self._drop(work, "cancelled")
            return
        if self.orders_today >= self.cfg.max_orders_day:
            raise L.Refused(f"order budget: {self.cfg.max_orders_day} orders a day")
        if "close" in intent:
            pos = self.positions.get(intent["close"]) if isinstance(intent["close"], int) else None
            if pos is None:
                raise L.Refused("close: no such open position")
            if pos.closing:
                raise L.Refused("close: this position already has a working close (cancel it first)")
            rules = day.rules[pos.root]
            if int(pos.expirations.min()) == day.ordinal and minute >= rules.close_cutoff:
                raise L.Refused(f"expiry cutoff: closing orders on expiring contracts end at {rules.close_cutoff // 60}:{rules.close_cutoff % 60:02d} ET")
            snap = day.snapshot(pos.root, mi)
            if snap is None:
                raise L.Refused("close: no chain for this root now")
            order = L.resolve_close(intent, pos.type, pos.legs_today(), pos.qty, snap, rules, position=pos.pid,
                                    stress=self.cfg.stress)
            work = Working(self._id(), order, order.qty, mi, arrival, self._expiry(order, arrival), 0.0, pid=pos.pid)
            self.orders[work.oid] = work
            pos.closing = work.oid
            self.orders_today += 1
            self.counts["orders"] += 1
            self.counts["closes"] += 1
            if order.tif == 0:
                self._ioc(day, work)
            return
        root = str(intent.get("root") or (self.roots[0] if len(self.roots) == 1 else "")).upper()
        if root not in self.roots:
            raise L.Refused(f"open: root {root or '?'} is not one this program trades ({', '.join(self.roots)}); name 'root'")
        snap = day.snapshot(root, mi)
        if snap is None:
            raise L.Refused(f"open: no {root} chain today")
        rules = day.rules[root]
        order = L.resolve_open(intent, snap, rules, buying_power=self.buying_power(), stress=self.cfg.stress)
        if any(leg.dte == 0 for leg in order.legs) and minute >= rules.open_cutoff:
            raise L.Refused(f"expiry cutoff: no new opening order on an expiring contract from {rules.open_cutoff // 60}:{rules.open_cutoff % 60:02d} ET")
        split = (getattr(day, "split_eve", None) or {}).get(root)
        if split is not None and any(leg.dte > 0 for leg in order.legs):
            # Counted in the result, never said to the program: the eve's close already keeps nothing across the split.
            raise Unsaid(f"stock split: an opening order held across {root}'s {split_label(split)} split")
        order.extra = {"minute": day.open_min + mi, "open_min": day.open_min, "context": self._context(day, snap, order)}
        work = Working(self._id(), order, order.qty, mi, arrival, self._expiry(order, arrival), order.reserve)
        self.orders[work.oid] = work
        self.orders_today += 1
        self.counts["orders"] += 1
        self.counts["opens"] += 1
        if order.tif == 0:
            self._ioc(day, work)

    def _ioc(self, day: DayData, work: Working) -> None:
        """An immediate-or-cancel order meets its arrival minute and no other."""
        work.expires_mi = work.arrival_mi

    @staticmethod
    def _expiry(order: L.Order, arrival: int) -> int | None:
        return None if order.tif is None else arrival + max(0, int(order.tif))

    def _context(self, day: DayData, snap: Snapshot, order: L.Order) -> dict:
        idx = np.array([leg.idx for leg in order.legs], dtype=np.int64)
        iv, delta, _, _, _ = snap.greeks_for(idx)
        strikes = [leg.strike for leg in order.legs]
        return {"spot": round(snap.spot, 4) if np.isfinite(snap.spot) else None, "minute": snap.minute,
                "weekday": day.weekday, "dte": int(min(leg.dte for leg in order.legs)),
                "moneyness": round((sum(strikes) / len(strikes)) / snap.spot - 1.0, 5) if np.isfinite(snap.spot) else None,
                "iv": [None if not np.isfinite(v) else round(float(v), 4) for v in iv],
                "delta": [None if not np.isfinite(v) else round(float(v), 4) for v in delta],
                "natural": round(order.natural, 4), "mid": round(order.mid, 4), "limit": round(order.limit, 4),
                "events": [k for k in EVENT_NAMES if day.events.get(k)]}

    # ------------------------------------------------------------------ the close
    def end_day(self, day: DayData, *, last: bool) -> None:
        for work in list(self.orders.values()):
            self._drop(work, "expired")
        close_mi = day.minutes - 1
        for pos in list(self.positions.values()):
            if int(pos.expirations.min()) == day.ordinal:
                self._expire(day, pos)
        for pos in list(self.positions.values()):
            self._mark(day, pos, close_mi)
        splitting = getattr(day, "split_eve", None)
        if splitting:
            self._split_eve(day, splitting)
        if last:
            for pos in list(self.positions.values()):
                if self.cfg.split_mark:
                    self._split_mark(day, pos)
                else:
                    self._window_end(day, pos)
            for pos, root, shares, ref in self.pending_shares:
                pos.info["share_gap"] = 0.0
                self._finish(pos, day)
            self.pending_shares = []
        for pos in self.positions.values():
            self._hold(pos.pid, pos.root, None, day.minutes - 1)  # still open: held to the close
        self._exposure(day)
        equity = self.equity()
        self.daily.append((day.day.isoformat(), round(equity - self.equity_prev, 6), round(equity, 6)))
        self.equity_prev = equity
        self.session += 1

    def _expire(self, day: DayData, pos: Position) -> None:
        """A position whose earliest leg expires today, at the close."""
        chain = day.chains.get(pos.root)
        level = settlement_level(chain.underlying) if chain is not None else math.nan
        if not math.isfinite(level):
            # No underlying today (a hole in the store): the position leaves at its last mark, and says so.
            value, fees = self._mark_exit(day, pos, day.minutes - 1)
            cash = value * venue.MULTIPLIER * pos.qty - fees
            self.cash += cash
            pos.cash += cash
            pos.fees += fees
            pos.exit_value_qty += value * pos.qty
            pos.exit_day, pos.exit_mi, pos.reason, pos.qty = day.ordinal, day.minutes - 1, "expired_without_data", 0
            self._finish(pos, day)
            return
        self._settle(day, pos, level, exit_day=day.ordinal, exit_mi=day.minutes - 1, late_legs_from_end=True)

    def _settle_missed(self, day: DayData, pos: Position) -> None:
        """A position whose expiry fell BETWEEN run days (no chain that day): settled against that day's
        recorded underlying, or, where the store has none, against today's first price as a data hole."""
        from .day import from_ordinal

        near = int(pos.expirations.min())
        expiry = from_ordinal(near)
        level, hole = math.nan, False
        if day.store is not None and day.store.has("underlying", pos.root, expiry):
            level = settlement_level(day.store.underlying(pos.root, expiry))
        if not math.isfinite(level):
            chain = day.chains.get(pos.root)
            known = chain.underlying.price[np.isfinite(chain.underlying.price)] if chain is not None else np.zeros(0)
            level, hole = (float(known[0]), True) if known.size else (math.nan, True)
        if not math.isfinite(level):
            pos.reason = "expired_without_data"
            value, fees = self._mark_exit(day, pos, None)   # its expiry was an earlier day: never today's chain
            cash = value * venue.MULTIPLIER * pos.qty - fees
            self.cash += cash
            pos.cash += cash
            pos.fees += fees
            pos.exit_value_qty += value * pos.qty
            pos.exit_day, pos.exit_mi, pos.qty = day.ordinal, 0, 0
            self._finish(pos, day)
            return
        self._settle(day, pos, level, exit_day=day.ordinal if hole else near, exit_mi=0 if hole else day.minutes - 1,
                     late_legs_from_end=False, hole=hole, shares_now=True)

    def _settle(self, day: DayData, pos: Position, level: float, *, exit_day: int, exit_mi: int, late_legs_from_end: bool,
                hole: bool = False, shares_now: bool = False) -> None:
        """Exercise and settle the earliest expiry at `level`: cash-settled index legs and equity legs at
        $0.01 in the money, an equity short leg assigned into shares (marked to the next session's first
        price; `shares_now` when that session is today). Legs expiring later (a calendar's back month)
        leave at their NATURAL price with their fees, never at a mid."""
        near = int(pos.expirations.min())
        value, shares, fees, later, itm = 0.0, 0.0, 0.0, False, False
        for leg, exp, i in zip(pos.legs, pos.expirations, pos.idx):
            if int(exp) != near:
                later = True
                price = self._leg_exit_price(day, pos.root, int(i), leg.side, from_end=late_legs_from_end)
                value += leg.side * leg.ratio * price
                fees += venue.leg_fee(pos.root, leg.ratio * pos.qty, price, sell=leg.side > 0)
                continue
            intrinsic = max(0.0, level - leg.strike) if leg.is_call else max(0.0, leg.strike - level)
            if not math.isfinite(intrinsic) or intrinsic < 0.01:
                continue
            itm = True
            value += leg.side * leg.ratio * intrinsic
            if not venue.is_index(pos.root):
                shares += (1.0 if leg.is_call else -1.0) * leg.side * leg.ratio * venue.MULTIPLIER * pos.qty
        cash = value * venue.MULTIPLIER * pos.qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += value * pos.qty
        pos.exit_day, pos.exit_mi = exit_day, exit_mi
        if later:
            pos.reason = "forced_mark"
        elif venue.is_index(pos.root):
            pos.reason = "settled_data_hole" if hole else "settled"
            self.counts["settled"] += 1
        elif not itm:
            pos.reason = "expired_data_hole" if hole else "expired"   # nothing in the money: no exercise, no fee
        else:
            pos.reason = "exercised_data_hole" if hole else "exercised"
            self.counts["exercised"] += 1
        pos.qty = 0
        if shares and not shares_now:
            pos.info["shares"] = shares
            self.positions.pop(pos.pid, None)
            self.pending_shares.append((pos, pos.root, shares, level))
            return
        if shares:
            chain = day.chains.get(pos.root)
            known = chain.underlying.price[np.isfinite(chain.underlying.price)] if chain is not None else np.zeros(0)
            gap = float(shares) * ((float(known[0]) if known.size else level) - level)
            self.cash += gap
            pos.cash += gap
            pos.info["shares"] = shares
            pos.info["share_gap"] = round(gap, 2)
        self._finish(pos, day)

    @staticmethod
    def _leg_exit_price(day: DayData, root: str, i: int, side: int, *, from_end: bool, back: int = 30) -> float:
        """What closing one leg gets at its natural: a long leg sold at its bid, a short bought at its ask;
        at the close (or the last quoted minute of the final half hour), or, `from_end` False, at the
        first quoted minute of the day. 0 for a long leg and nothing known; the short's ask unknown is
        taken at the leg's last value the engine can see, else 0 (a short back month is rare)."""
        chain = day.chains.get(root)
        if chain is None or i < 0:
            return 0.0
        minutes = range(day.minutes - 1, max(-1, day.minutes - 1 - back), -1) if from_end else range(1, min(day.minutes, 1 + back))
        for m in minutes:
            bid, ask = float(chain.bid[m, i]), float(chain.ask[m, i])
            if math.isfinite(bid) and math.isfinite(ask):
                return bid if side > 0 else ask
        return 0.0

    def _mark(self, day: DayData, pos: Position, mi: int) -> None:
        chain = day.chains.get(pos.root)
        if chain is None or (pos.idx < 0).any():
            return
        for m in range(mi, max(0, mi - 30), -1):
            bid = chain.bid[m, pos.idx]
            ask = chain.ask[m, pos.idx]
            if np.isfinite(bid).all() and np.isfinite(ask).all():
                sides = np.array([leg.side * leg.ratio for leg in pos.legs], dtype=np.float64)
                self._set_mark(pos, float(np.sum(sides * 0.5 * (bid + ask))))
                break
        # The day's last price the package traded at, for an exit at a mark on a later day (`_fallback_close`).
        found = self._last_close(day, pos, mi)
        if found is not None:
            pos.info["close_at"] = [found[0], found[1], int(day.ordinal), int(found[2])]

    @staticmethod
    def _set_mark(pos: Position, value: float) -> None:
        """The position's mark: a mid inside what the package can be worth at expiry. A mid outside it (a blown-out
        leg's) is no price: the mark stays at the last one inside, and `mark_out` in the position's info (saved with
        it) says so until a mid inside comes back. Never clamped to a bound: a quote blown out in the position's favour
        would mark it at the package's most."""
        lo, hi = pos.bounds()
        if lo - 1e-9 <= value <= hi + 1e-9:
            pos.last_mark = value
            pos.info.pop("mark_out", None)
        else:
            pos.info["mark_out"] = True

    def _last_close(self, day: DayData, pos: Position, mi: int | None) -> tuple[float, list[float], int] | None:
        """The latest minute at or before `mi` of today's chain whose close natural (at the run's stress) is a price
        the package trades at (`_tradeable`): (that natural, its legs' close prices for the fees, the minute). None when
        today has none, or no chain holds the position's legs."""
        chain = day.chains.get(pos.root)
        if mi is None or chain is None or pos.idx is None or (pos.idx < 0).any():
            return None
        lo, hi = pos.bounds()
        stress = self.cfg.stress
        for m in range(min(int(mi), day.minutes - 1), -1, -1):
            bid, ask = chain.bid[m, pos.idx], chain.ask[m, pos.idx]
            if not (np.isfinite(bid).all() and np.isfinite(ask).all()):
                continue
            value, prices = 0.0, []
            for leg, b, a in zip(pos.legs, bid.tolist(), ask.tolist()):
                prices.append(b if leg.side > 0 else a)
                if stress != 1.0:   # `legs.natural_value`'s stress: every half-spread widened
                    mid, half = 0.5 * (b + a), 0.5 * (a - b) * stress
                    b, a = max(0.0, mid - half), mid + half
                value += leg.side * leg.ratio * (b if leg.side > 0 else a)
            if self._tradeable(value, lo, hi, False):
                return value, prices, m
        return None

    def _fallback_close(self, day: DayData, pos: Position, mi: int | None) -> tuple[float, float]:
        """(value a share, fees) of the honest exit when the latest quote is no price for the package: the last price it
        traded at, the latest tradeable close natural at or before `mi` today (`_last_close`), else the one a day's
        close recorded before (`_mark`), with its fees, held at the package's least like any close. With neither, its
        last mark (else its entry) and no fee. The trade is flagged `bounded`."""
        pos.info["bounded"] = True
        lo, hi = pos.bounds()
        found = self._last_close(day, pos, mi)
        if found is None:
            stored = pos.info.get("close_at")
            if stored and (int(stored[2]) < day.ordinal or (mi is not None and int(stored[3]) <= mi)):
                found = (float(stored[0]), [float(x) for x in stored[1]], int(stored[3]))
        if found is None:
            raw = pos.last_mark if math.isfinite(pos.last_mark) else pos.entry
            return min(max(raw, lo), hi), 0.0
        value, prices, _ = found
        if value < lo:
            self.counts["bounded_close"] += 1
            value = lo
        return value, L.order_fees(pos.root, pos.legs, prices, pos.qty, "close")

    def _mark_exit(self, day: DayData, pos: Position, mi: int | None) -> tuple[float, float]:
        """(value a share, fees) of an exit at the position's mark (a split, a window end with no quote, a data hole):
        its mark with no fee, an accounting value as the day's equity counts it; but when the latest mid was outside the
        package's range (`mark_out`), the mark is stale and the exit is `_fallback_close`'s."""
        if pos.info.get("mark_out"):
            return self._fallback_close(day, pos, mi)
        lo, hi = pos.bounds()
        raw = pos.last_mark if math.isfinite(pos.last_mark) else pos.entry
        value = min(max(raw, lo), hi)   # inside by construction; a state saved before the rule may hold one outside
        if value != raw:
            pos.info["bounded"] = True
        return value, 0.0

    def _split_mark(self, day: DayData, pos: Position) -> None:
        """The end of a segment another segment continues: the position is valued at its mid (the close's
        mark, as the day's equity already counts it) with no fee. An accounting split, not a trade: the
        segment's daily P&L is the unsplit run's, and the next segment starts without it. When the close's mid was
        outside the package's range, the last price it traded at, with its fees (`_mark_exit`)."""
        value, fees = self._mark_exit(day, pos, day.minutes - 1)
        cash = value * venue.MULTIPLIER * pos.qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += value * pos.qty
        pos.qty = 0
        pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, day.minutes - 1, "split_mark"
        self._finish(pos, day)

    def _split_eve(self, day: DayData, splitting: Mapping[str, float]) -> None:
        """The close of a split's eve (the module docstring): every position on a splitting root still open is closed
        at the natural of the session's last quoted minute (`_split_close`); shares an expiry on it left pending are
        marked at today's settlement level (no gap), as at a window's end: nothing on the root is held across."""
        for pos in list(self.positions.values()):
            if pos.root in splitting:
                self._split_close(day, pos)
        keep = []
        for pos, root, shares, ref in self.pending_shares:
            if root in splitting:
                pos.info["share_gap"] = 0.0
                self._finish(pos, day)
            else:
                keep.append((pos, root, shares, ref))
        self.pending_shares = keep

    def _split_close(self, day: DayData, pos: Position, back: int = 30) -> None:
        """Close one position on a split's eve at the natural of the session's last minute that quotes every leg (the
        last stepped minute, or up to `back` minutes before it), stress applied, with its fees (`stock_split`). Where no
        such minute exists, leg by leg (`stock_split_legs`): each leg at its own last quoted natural in those minutes,
        stress applied, else at its intrinsic value at the eve's level, with each leg's fee."""
        legs = pos.legs_today()
        chain = day.chains.get(pos.root)
        value, fees, at, reason = math.nan, 0.0, day.minutes - 2, "stock_split"
        lo, hi = pos.bounds()
        if chain is not None and all(leg.idx >= 0 for leg in legs):
            for mi in range(day.minutes - 2, max(0, day.minutes - 2 - back), -1):
                snap = day.snapshot(pos.root, mi)
                if snap is None:
                    break
                natural, _ = L.natural_value(snap, legs, "close", stress=self.cfg.stress)
                if not math.isfinite(natural):
                    continue
                plain = natural if self.cfg.stress == 1.0 else L.natural_value(snap, legs, "close")[0]
                if not self._tradeable(plain, lo, hi, False):
                    self.counts["blocked_out_of_range"] += 1   # over the package's most: no market this minute
                    continue
                bounded = self._in_bounds(natural, lo, hi, False)
                if bounded != natural:
                    self.counts["bounded_close"] += 1
                    pos.info["bounded"] = True
                prices = [float(snap.bid[leg.idx] if leg.side > 0 else snap.ask[leg.idx]) for leg in legs]
                value, fees, at = bounded, L.order_fees(pos.root, legs, prices, pos.qty, "close"), mi
                break
        if not math.isfinite(value):
            level = settlement_level(chain.underlying) if chain is not None else math.nan
            value, fees, reason = 0.0, 0.0, "stock_split_legs"
            for leg in legs:
                price = self._leg_natural(day, pos.root, leg, back)
                if not math.isfinite(price):
                    intrinsic = (level - leg.strike) if leg.is_call else (leg.strike - level)
                    price = max(0.0, intrinsic) if math.isfinite(intrinsic) else 0.0
                value += leg.side * leg.ratio * price
                fees += venue.leg_fee(pos.root, leg.ratio * pos.qty, price, sell=leg.side > 0)
            fees = round(fees, 2)
            if not lo - 1e-9 <= value <= hi + 1e-9:
                pos.info["bounded"] = True
                value = min(max(value, lo), hi)
        cash = value * venue.MULTIPLIER * pos.qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += value * pos.qty
        pos.qty = 0
        pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, at, reason
        self._finish(pos, day)

    def _leg_natural(self, day: DayData, root: str, leg: L.LegFill, back: int) -> float:
        """What closing one leg gets at its natural in the session's last `back` stepped minutes (a long leg sold at its
        bid, a short one bought at its ask; stress widens the half-spread); NaN when it has no quote there."""
        chain = day.chains.get(root)
        if chain is None or leg.idx < 0:
            return math.nan
        for mi in range(day.minutes - 2, max(0, day.minutes - 2 - back), -1):
            bid, ask = float(chain.bid[mi, leg.idx]), float(chain.ask[mi, leg.idx])
            if math.isfinite(bid) and math.isfinite(ask):
                if self.cfg.stress != 1.0:
                    mid, half = 0.5 * (bid + ask), 0.5 * (ask - bid) * self.cfg.stress
                    bid, ask = max(0.0, mid - half), mid + half
                return bid if leg.side > 0 else ask
        return math.nan

    def _window_end(self, day: DayData, pos: Position) -> None:
        snap = day.snapshot(pos.root, day.minutes - 2) if pos.root in day.chains else None
        legs = pos.legs_today()
        value = math.nan
        fees = 0.0
        blocked = False
        if snap is not None and all(leg.idx >= 0 for leg in legs):
            value, _ = L.natural_value(snap, legs, "close", stress=self.cfg.stress)
            if math.isfinite(value):
                # The close's own rule (`_in_bounds`): never below the package's least; above its most, no close.
                lo, hi = pos.bounds()
                bounded = self._in_bounds(value, lo, hi, False)
                if bounded is None:
                    # Over the package's most: no close there. It leaves at the last price the package traded at
                    # today, with its fees, never at a mark the blown-out quote moved.
                    self.counts["blocked_out_of_range"] += 1
                    value, fees = self._fallback_close(day, pos, day.minutes - 2)
                    blocked = True
                elif bounded != value:
                    self.counts["bounded_close"] += 1
                    pos.info["bounded"] = True
                    value = bounded
            if math.isfinite(value) and not blocked:
                prices = [float(snap.bid[leg.idx] if leg.side > 0 else snap.ask[leg.idx]) for leg in legs]
                fees = L.order_fees(pos.root, legs, prices, pos.qty, "close")
        reason = "window_end"
        if not math.isfinite(value):
            value, fees = self._mark_exit(day, pos, day.minutes - 2)
            reason = "window_end_mark"
        cash = value * venue.MULTIPLIER * pos.qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += value * pos.qty
        pos.qty = 0
        pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, day.minutes - 2, reason
        self._finish(pos, day)


# --------------------------------------------------------------------------- identity
_CODE_DIGEST: str | None = None


def code_digest() -> str:
    """A hash of the engine's code: every file of league/gym and the league modules it imports (the
    same files the sealed-box bundle carries)."""
    global _CODE_DIGEST
    if _CODE_DIGEST is None:
        import hashlib
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        files = [repo / "league" / name for name in ("__init__.py", "safety.py", "structure_core.py", "stats.py")]
        files += sorted(p for p in (repo / "league" / "gym").rglob("*.py") if "__pycache__" not in p.parts)
        digest = hashlib.sha256()
        for path in sorted(files, key=lambda p: p.relative_to(repo).as_posix()):
            digest.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        _CODE_DIGEST = digest.hexdigest()[:16]
    return _CODE_DIGEST


def tables_digest() -> str:
    """A hash of the tables a run depends on beyond the store: events, rates, stock splits, fees, ticks, the fill seed."""
    import hashlib
    import json

    from . import events as EV

    body = {"fomc": sorted(d.isoformat() for d in EV.FOMC), "cpi": sorted(d.isoformat() for d in EV.CPI),
            "jobs": sorted(d.isoformat() for d in EV.JOBS), "rates": [[d.isoformat(), r] for d, r in EV.RATES],
            "fees": [venue.OCC_FEE, venue.ORF_FEE, venue.CAT_FEE, venue.TAF_FEE, venue.SEC_RATE, venue.INDEX_FEE,
                     sorted(venue.EXCHANGE_FEE.items()), venue.XSP_LARGE_ORDER_FEE],
            "ticks": [sorted(venue.PENNY_ALL), sorted(venue.NICKEL), venue.NET_TICK], "seed": F.SEED,
            "splits": [[root, day.isoformat(), factor] for root, day, factor in EV.SPLITS]}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- the run
def _close_day(data: DayData, history: History, seen: dict[str, dt.date] | None = None) -> None:
    """The end of a replayed day: its underlying joins the history (`seen`: each root's last session in it), then the
    day is closed (`DayData.close`). A function of its own so no loop variable of `run` keeps one of the day's chains
    alive into the next."""
    for root, chain in data.chains.items():
        if history.add(root, chain.underlying.price) and seen is not None:
            seen[root] = data.day
    data.close()


def _split_alerts(data: DayData, history: History, seen: Mapping[str, dt.date]) -> list[dict[str, Any]]:
    """Today's price cross-check (`split_alert`) of each root with a chain, from what the replay already holds: the
    history's last close and today's first price. Nothing is read ahead."""
    out = []
    for root, chain in data.chains.items():
        closes = history.arrays(root, 1)[3]
        price = chain.underlying.price
        known = price[np.isfinite(price)]
        if closes.size and known.size:
            alert = split_alert(root, seen.get(root), float(closes[-1]), data.day, float(known[0]))
            if alert is not None:
                out.append(alert)
    return out


def run(programs: Sequence[Program], store: "Store", cfg: RunConfig, *, days: Sequence[dt.date] | None = None,
        progress: Any = None, keep: list | None = None) -> list[dict]:
    """Run a batch of programs over the window, day-major; return one result dict per program
    (`results.build`), in the order given. `keep`, a list, receives the accounts (for inspection)."""
    from . import results as R

    began = time.perf_counter()
    universe = tuple(r.upper() for r in cfg.roots)
    accounts: list[Account] = []
    for program in programs:
        roots = tuple(r for r in program.needs.roots if not universe or r in universe)
        accounts.append(Account(program, cfg, roots))
    if keep is not None:
        keep.extend(accounts)
    all_roots = tuple(sorted({r for a in accounts for r in a.roots}))
    if days is None:
        days = [d for d in store.days(cfg.window, [], start=cfg.start, end=cfg.end)
                if any(store.has("nbbo", r, d) for r in all_roots)] if all_roots else []
    days = list(days)
    warm: list[dt.date] = []
    if days and cfg.warmup > 0:
        # The window's trading days just before the first (never another window's: no leak across the line).
        warm = [d for d in store.days(cfg.window, [], end=days[0] - dt.timedelta(days=1))
                if any(store.has("nbbo", r, d) for r in all_roots)][-int(cfg.warmup):]
    for day in warm + days:
        store.check(day)
    depth = max([a.needs.history for a in accounts] + [11])
    history = History(depth)
    seen: dict[str, dt.date] = {}   # each root's last session in the history (the split cross-check)
    if days:
        for prior in store.history_days((warm or days)[0], depth):
            for root in all_roots:
                if store.has("underlying", root, prior):
                    if history.add(root, store.underlying(root, prior).price):
                        seen[root] = prior
    events = EventCalendar(store.trading_days(), store.session)
    regimes: dict[str, dict[str, dict[str, float]]] = {}
    from .day import ordinal as to_ordinal

    applied = split_eves(store, all_roots, days) if days else []
    eves: dict[dt.date, dict[str, float]] = {}
    for split in applied:
        eves.setdefault(split["eve"], {})[split["root"]] = split["factor"]
    alerts: list[dict[str, Any]] = []

    for day in warm:
        data = DayData(store, day, all_roots, events, history, to_ordinal(day))
        live = [a for a in accounts if a.roots and not a.runner.disqualified]
        schedules = [account.decision_minutes(data) for account in live]
        for account, schedule in zip(live, schedules):
            account.warming = True
            for root in account.roots:
                data.want(root, schedule)
        for mi in range(1, data.minutes - 1):
            data.advance(mi)
            for account, schedule in zip(live, schedules):
                if mi in schedule and not account.runner.disqualified:
                    account._decide(data, mi)
        for account in live:
            account.warming = False
            account.closed_since, account.rejects_since = [], []
        _close_day(data, history, seen)

    for n, day in enumerate(days):
        data = DayData(store, day, all_roots, events, history, to_ordinal(day), split_eve=eves.get(day))
        alerts += _split_alerts(data, history, seen)
        live = [a for a in accounts if a.roots]
        for account in live:
            account.begin_day(data)
        schedules = [account.decision_minutes(data) for account in live]
        for account, schedule in zip(live, schedules):
            for root in account.roots:
                data.want(root, schedule)
        regimes[day.isoformat()] = {root: data.regime(root) for root in data.chains}
        events_minutes = set()
        for rules in data.rules.values():
            for minute in (rules.open_cutoff, rules.close_cutoff, rules.liquidation):
                if minute is not None and data.open_min < minute < data.close_min:
                    events_minutes.update(range(minute - data.open_min, data.minutes - 1) if minute == rules.liquidation
                                          else [minute - data.open_min])
            if rules.expiry_close is not None:  # the House's expiry close: every minute up to the close cutoff
                events_minutes.update(range(max(1, rules.expiry_close - data.open_min), rules.close_cutoff - data.open_min))
        for mi in range(1, data.minutes - 1):
            data.advance(mi)
            for account, schedule in zip(live, schedules):
                wants = mi in schedule
                if wants or account.orders or (account.positions and mi in events_minutes):
                    account.step(data, mi, wants)
        for account in live:
            account.end_day(data, last=n == len(days) - 1)
        _close_day(data, history, seen)
        if progress is not None:
            progress(n + 1, len(days), day)
    for account in accounts:
        # The result's `stock_splits` block, only when a split of the table fell on the account's roots in the run, or the
        # price cross-check raised an alert on one of them: a run with neither returns exactly what it did before.
        mine = {"applied": [{**s, "eve": s["eve"].isoformat()} for s in applied if s["root"] in account.roots],
                "alerts": [a for a in alerts if a["root"] in account.roots]}
        account.stock_splits = {k: v for k, v in mine.items() if v}
    elapsed = time.perf_counter() - began
    data_version = store.data_version(all_roots, warm + days) if days else "no-days"
    code, tables = code_digest(), tables_digest()
    return [R.build(a, cfg, days, data_version, regimes, elapsed / max(1, len(accounts)), code=code, tables=tables)
            for a in accounts]


__all__ = ["RunConfig", "run", "Account", "DayData", "DayClosed", "History", "Unsaid", "split_factor", "split_eves", "split_alert",
           "split_check", "split_label"]
